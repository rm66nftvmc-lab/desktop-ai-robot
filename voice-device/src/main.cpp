#include <Arduino.h>
#include <SPI.h>
#include <driver/i2s.h>
#include <esp_system.h>
#include <esp_heap_caps.h>

#include "faces.h"
#include "qiuqiu_assets.h"
#include "qiuqiu_motion.h"
#include <math.h>
#include <atomic>

// USB CDC: A5 5A | type | seq LE | length LE | payload | CRC16-CCITT LE.
static constexpr uint8_t FRAME_STATUS=1, FRAME_DISPLAY=2, FRAME_AUDIO_UP=3, FRAME_AUDIO_DOWN=4;
static constexpr uint8_t FRAME_HEARTBEAT=5, FRAME_BUTTON=6, FRAME_ACK=8;
static constexpr uint8_t FRAME_HELLO=9, FRAME_WELCOME=10, FRAME_AUDIO_END=11, FRAME_FACE=12;
static constexpr uint8_t FRAME_ANIMATION=13;
static constexpr uint8_t FRAME_THEME=14;
static constexpr uint8_t displayTheme=1; // Emotion Ball is the only installed display.
static std::atomic<int> pendingFace{-1},pendingColor{-1};
static bool screenTaskRunning=false;
static constexpr uint16_t MAX_PAYLOAD=1024;
static constexpr int KEY_PIN=1, SAMPLE_RATE=16000;
static constexpr int LCD_CS=8, LCD_DC=9, LCD_RST=10, LCD_MOSI=11, LCD_SCLK=12;
static constexpr int LCD_WIDTH=240, LCD_HEIGHT=320;
static SPISettings lcdSpi(40000000, MSBFIRST, SPI_MODE0);
static bool micReady=false,speakerReady=false;
static std::atomic<bool> connected{false},listening{false},playing{false};
static uint16_t txSequence=0;
static uint32_t lastHost=0, lastHello=0, lastStatus=0;
static uint32_t receivedAudio=0, sentAcks=0, badCrc=0;
static uint8_t rxBuffer[9+MAX_PAYLOAD];
static size_t rxLength=0;
static uint8_t lcdRowBytes[LCD_WIDTH*2];
static std::atomic<uint8_t> currentFaceFrame{0};
static std::atomic<bool> animationEnabled{true};
static uint8_t *lcdFrameBytes=nullptr;
static constexpr uint16_t lcdCachedFrames=0; // Legacy telemetry field; no character frame cache.
static std::atomic<uint32_t> lcdComposeUs{0},lcdPushUs{0};
static std::atomic<uint32_t> lcdPresents{0},lcdSourceUpdates{0};

static uint16_t crcStep(uint16_t crc, const uint8_t *data, size_t length) {
  for (size_t i=0; i<length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (int bit=0; bit<8; ++bit)
      crc = crc & 0x8000 ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

static void sendFrame(uint8_t kind, const uint8_t *payload=nullptr, uint16_t length=0) {
  if (length>MAX_PAYLOAD || !Serial) return;
  uint8_t header[7]={0xA5,0x5A,kind,
    static_cast<uint8_t>(txSequence),static_cast<uint8_t>(txSequence>>8),
    static_cast<uint8_t>(length),static_cast<uint8_t>(length>>8)};
  ++txSequence;
  uint16_t crc=crcStep(0xFFFF,header+2,5);
  if (length) crc=crcStep(crc,payload,length);
  uint8_t trailer[2]={static_cast<uint8_t>(crc),static_cast<uint8_t>(crc>>8)};
  Serial.write(header,sizeof(header));
  if (length) Serial.write(payload,length);
  Serial.write(trailer,sizeof(trailer));
}

static void sendJson(uint8_t kind,const char *json) {
  sendFrame(kind,reinterpret_cast<const uint8_t *>(json),strlen(json));
}

static void lcdCommand(uint8_t command,const uint8_t *data=nullptr,size_t length=0) {
  SPI.beginTransaction(lcdSpi);
  digitalWrite(LCD_CS,LOW); digitalWrite(LCD_DC,LOW);
  SPI.transfer(command);
  if (length) {
    digitalWrite(LCD_DC,HIGH);
    for (size_t i=0;i<length;++i) SPI.transfer(data[i]);
  }
  digitalWrite(LCD_CS,HIGH); SPI.endTransaction();
}

static void lcdSetWindow(int x0,int y0,int x1,int y1) {
  const uint8_t columns[]={static_cast<uint8_t>(x0>>8),static_cast<uint8_t>(x0),
                           static_cast<uint8_t>(x1>>8),static_cast<uint8_t>(x1)};
  const uint8_t rows[]={static_cast<uint8_t>(y0>>8),static_cast<uint8_t>(y0),
                        static_cast<uint8_t>(y1>>8),static_cast<uint8_t>(y1)};
  lcdCommand(0x2A,columns,sizeof(columns));
  lcdCommand(0x2B,rows,sizeof(rows));
}

static void lcdBeginPixels() {
  SPI.beginTransaction(lcdSpi);
  digitalWrite(LCD_CS,LOW); digitalWrite(LCD_DC,LOW); SPI.transfer(0x2C);
  digitalWrite(LCD_DC,HIGH);
}

static void lcdEndPixels() {
  digitalWrite(LCD_CS,HIGH); SPI.endTransaction();
}

static void lcdFillRect(int x0,int y0,int x1,int y1,uint16_t color) {
  if (x1<x0 || y1<y0) return;
  lcdSetWindow(x0,y0,x1,y1);
  const int width=x1-x0+1;
  for (int x=0;x<width;++x) {
    lcdRowBytes[x*2]=color>>8;
    lcdRowBytes[x*2+1]=color&0xFF;
  }
  lcdBeginPixels();
  for (int y=y0;y<=y1;++y) SPI.writeBytes(lcdRowBytes,width*2);
  lcdEndPixels();
}

static void lcdFill(uint16_t color) {
  lcdFillRect(0,0,LCD_WIDTH-1,LCD_HEIGHT-1,color);
}

static std::atomic<int> currentFace{-1};

// Every update is opaque and precomposed. Only theme entry transfers the full
// sphere; normal updates touch the eye/mouth area, including while recording.
static qiuqiu::Motion qiuqiuMotion;
static bool qiuqiuNeedsFull=true;
static std::atomic<float> speakerEnvelope{0};
static uint8_t *qiuqiuBase=nullptr;
static uint8_t *qiuqiuPrevious=nullptr;
static bool qiuqiuPreviousValid=false;
static constexpr int QX=42,QY=38,QW=105,QH=114,QT=8;
static std::atomic<uint32_t> qiuqiuPixelBytes{0};
static std::atomic<uint16_t> qiuqiuDirtyTiles{0};
static std::atomic<uint32_t> speakerEnvelopeAt{0};

static qiuqiu::Mood qiuqiuMood() {
  switch(currentFace.load()) {
    case FACE_ID_LISTEN:return qiuqiu::Mood::Listen;
    case FACE_ID_THINK:return qiuqiu::Mood::Think;
    case FACE_ID_SPEAK:return qiuqiu::Mood::Speak;
    case FACE_ID_SLEEP:return qiuqiu::Mood::Sleep;
    case FACE_ID_APPROVE:return qiuqiu::Mood::Approve;
    case FACE_ID_ERROR:return qiuqiu::Mood::Error;
    default:return qiuqiu::Mood::Idle;
  }
}

static void qiuqiuInk(int x,int y,float coverage) {
  if (x<40||x>153||y<42||y>146||coverage<=0) return;
  coverage=fminf(1.f,coverage);
  const int offset=((191-x)*192+y)*2;
  uint16_t bg=(lcdFrameBytes[offset]<<8)|lcdFrameBytes[offset+1];
  uint16_t fg=0x2125;
  int r=((bg>>11)&31)*(1-coverage)+((fg>>11)&31)*coverage;
  int g=((bg>>5)&63)*(1-coverage)+((fg>>5)&63)*coverage;
  int b=(bg&31)*(1-coverage)+(fg&31)*coverage;
  uint16_t color=(r<<11)|(g<<5)|b;
  lcdFrameBytes[offset]=color>>8; lcdFrameBytes[offset+1]=color;
}

// Compare final RGB565 pixels, including antialiasing and erased old features.
// Never send a base-only intermediate image. Unchanged tiles stay in LCD RAM.
static bool qiuqiuPresent(bool full) {
  bool wrote=false;
  qiuqiuDirtyTiles=0;
  auto push=[&](int x,int y,int width,int height) {
    lcdSetWindow(24+x,64+y,24+x+width-1,64+y+height-1);
    lcdBeginPixels();
    for(int row=y;row<y+height;++row)
      SPI.writeBytes(lcdFrameBytes+(row*192+x)*2,width*2);
    lcdEndPixels();
    qiuqiuPixelBytes.fetch_add(width*height*2);
    wrote=true;
  };
  if(full || !qiuqiuPrevious || !qiuqiuPreviousValid) {
    if(full) push(0,0,192,192); else push(QX,QY,QW,QH);
  } else {
    constexpr int columns=(QW+QT-1)/QT,rows=(QH+QT-1)/QT;
    bool changed[rows][columns]={};
    uint16_t count=0;
    for(int ty=0;ty<rows;++ty) for(int tx=0;tx<columns;++tx) {
      int x=tx*QT,width=min(QT,QW-x),bottom=min(QH,(ty+1)*QT);
      for(int y=ty*QT;y<bottom;++y) {
        if(memcmp(lcdFrameBytes+((QY+y)*192+QX+x)*2,
                  qiuqiuPrevious+(y*QW+x)*2,width*2)!=0) {
          changed[ty][tx]=true;++count;break;
        }
      }
    }
    qiuqiuDirtyTiles=count;
    // Merge neighboring changed tiles, never bridge a clean tile. Commands
    // remain bounded, and RGB565 quantization can skip unchanged frames.
    for(int ty=0;ty<rows;++ty) for(int tx=0;tx<columns;) {
      if(!changed[ty][tx]) {++tx;continue;}
      int first=tx;
      while(tx<columns && changed[ty][tx]) ++tx;
      int left=first*QT,right=min(QW,tx*QT);
      push(QX+left,QY+ty*QT,right-left,min(QT,QH-ty*QT));
    }
  }
  if(qiuqiuPrevious) {
    for(int y=0;y<QH;++y)
      memcpy(qiuqiuPrevious+y*QW*2,lcdFrameBytes+((QY+y)*192+QX)*2,QW*2);
    qiuqiuPreviousValid=true;
  }
  return wrote;
}

static void lcdDrawQiuqiu() {
  if (!lcdFrameBytes) return;
  const uint32_t started=micros(),now=millis();
  const bool full=qiuqiuNeedsFull;
  // Logical bounds cover every pose and its antialiased edge. Rebuild from
  // texture each time so no eye, mouth or dot trails survive a transition.
  const int lx0=full?0:40,lx1=full?191:153,ly0=full?0:42,ly1=full?191:146;
  const int x0=ly0,x1=ly1,y0=191-lx1,y1=191-lx0;
  const int rowBytes=(x1-x0+1)*2;
  if (qiuqiuBase) {
    for (int y=y0;y<=y1;++y)
      memcpy(lcdFrameBytes+(y*192+x0)*2,qiuqiuBase+(y*192+x0)*2,rowBytes);
  } else {
    for (int y=ly0;y<=ly1;++y) for (int x=lx0;x<=lx1;++x) {
      uint16_t color=pgm_read_word(&QIUQIU_TEXTURE[y*192+x]);
      const int offset=((191-x)*192+y)*2;
      lcdFrameBytes[offset]=color>>8; lcdFrameBytes[offset+1]=color;
    }
  }
  float energy=(playing && now-speakerEnvelopeAt<180)?speakerEnvelope.load():0;
  const auto &pose=qiuqiuMotion.step(qiuqiuMood(),now,energy);
  for (const auto &e:pose.eyes) {
    const float norm=1/sqrtf(1+e.tilt*e.tilt);
    const float extentX=e.radius+fabsf(e.tilt)*e.half+2;
    for (int y=int(e.y-e.half-e.radius-2);y<=int(e.y+e.half+e.radius+2);++y)
      for (int x=int(e.x-extentX);x<=int(e.x+extentX);++x) {
        float dx=x-e.x,dy=y-e.y;
        // Normalize rotation so eye thickness doesn't change with tilt.
        float u=(dx-e.tilt*dy)*norm,v=(dy+e.tilt*dx)*norm;
        float q=fmaxf(0.f,fabsf(v)-e.half);
        qiuqiuInk(x,y,e.radius+.5f-sqrtf(u*u+q*q));
      }
  }
  for(int i=0;i<3;++i) if (pose.dots[i]>.002f) for(int y=47;y<=55;++y) for(int x=84+i*12;x<=92+i*12;++x) {
    float dx=x-(88+i*12),dy=y-51;
    qiuqiuInk(x,y,fminf(1.f,fmaxf(0.f,3.4f-sqrtf(dx*dx+dy*dy)))*pose.dots[i]);
  }
  // Speech energy comes from PCM sent to I2S; silent gaps close the mouth.
  float ry=1+pose.mouth*8;
  if (pose.mouth>.002f) for(int y=118;y<=138;++y) for(int x=83;x<=109;++x) {
    float dx=(x-96)/10.f,dy=(y-128)/ry;
    qiuqiuInk(x,y,fminf(1.f,fmaxf(0.f,(1-sqrtf(dx*dx+dy*dy))*ry))*fminf(1.f,pose.mouth*5));
  }
  lcdComposeUs=micros()-started;
  ++lcdSourceUpdates;
  const uint32_t pushStarted=micros();
  if(qiuqiuPresent(full)) ++lcdPresents;
  lcdPushUs=micros()-pushStarted;
  ++currentFaceFrame;
  qiuqiuNeedsFull=false;
}

static void lcdApplyFace(int index) {
  if (index<0 || index>=FACE_COUNT || index==currentFace) return;
  currentFace=index;
  currentFaceFrame=0;
  lcdDrawQiuqiu();
}

static void lcdTickAnimation() {
  static uint32_t lastQiuqiuUs=0;
  const uint32_t now=micros(),passed=now-lastQiuqiuUs;
  if (!animationEnabled) {lastQiuqiuUs=now;return;}
  if (passed<16667) return;
  lastQiuqiuUs+=passed/16667*16667;
  lcdDrawQiuqiu();
}

static void lcdDrawFace(int index) {
  if(index>=0 && index<FACE_COUNT) pendingFace.store(index);
}

// SPI and Emotion Ball pixel composition have exactly one owner. Audio I2S
// writes on the Arduino core cannot block this task's display cadence.
static void lcdService() {
  int face=pendingFace.exchange(-1);
  if(face>=0) lcdApplyFace(face);
  int color=pendingColor.exchange(-1);
  if(color>=0) {lcdFill(color);qiuqiuNeedsFull=true;qiuqiuPreviousValid=false;}
  lcdTickAnimation();
}

static void lcdTask(void *) {
  for(;;) {lcdService();vTaskDelay(1);}
}

static void lcdInit() {
  const size_t frameBytes=192*192*2;
  lcdFrameBytes=static_cast<uint8_t *>(heap_caps_malloc(frameBytes,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
  if (!lcdFrameBytes)
    lcdFrameBytes=static_cast<uint8_t *>(heap_caps_malloc(frameBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  qiuqiuPrevious=static_cast<uint8_t *>(heap_caps_malloc(QW*QH*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  qiuqiuBase=static_cast<uint8_t *>(heap_caps_malloc(192*192*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  if(qiuqiuBase) for(int y=0;y<192;++y) for(int x=0;x<192;++x) {
    uint16_t c=pgm_read_word(&QIUQIU_TEXTURE[y*192+x]);
    int offset=((191-x)*192+y)*2;
    qiuqiuBase[offset]=c>>8;qiuqiuBase[offset+1]=c;
  }
  pinMode(LCD_CS,OUTPUT); pinMode(LCD_DC,OUTPUT); pinMode(LCD_RST,OUTPUT);
  digitalWrite(LCD_CS,HIGH); digitalWrite(LCD_DC,HIGH); digitalWrite(LCD_RST,HIGH);
  SPI.begin(LCD_SCLK,-1,LCD_MOSI,LCD_CS);
  digitalWrite(LCD_RST,LOW); delay(20); digitalWrite(LCD_RST,HIGH); delay(120);
  lcdCommand(0x01); delay(150); lcdCommand(0x11); delay(120);
  const uint8_t rgb565=0x55, orientation=0;
  lcdCommand(0x3A,&rgb565,1); lcdCommand(0x36,&orientation,1);
  lcdCommand(0x21); lcdCommand(0x13); delay(10); lcdCommand(0x29); delay(100);
  lcdFill(0x0843);
}

static bool startMicrophone() {
  i2s_config_t config={};
  config.mode=static_cast<i2s_mode_t>(I2S_MODE_MASTER|I2S_MODE_RX);
  config.sample_rate=SAMPLE_RATE;
  config.bits_per_sample=I2S_BITS_PER_SAMPLE_32BIT;
  config.channel_format=I2S_CHANNEL_FMT_RIGHT_LEFT;
  config.communication_format=I2S_COMM_FORMAT_STAND_I2S;
  config.dma_buf_count=4; config.dma_buf_len=256;
  if (i2s_driver_install(I2S_NUM_0,&config,0,nullptr)!=ESP_OK) return false;
  i2s_pin_config_t pins={};
  pins.mck_io_num=I2S_PIN_NO_CHANGE; pins.bck_io_num=4; pins.ws_io_num=5;
  pins.data_out_num=I2S_PIN_NO_CHANGE; pins.data_in_num=6;
  if (i2s_set_pin(I2S_NUM_0,&pins)!=ESP_OK) {
    i2s_driver_uninstall(I2S_NUM_0); return false;
  }
  i2s_zero_dma_buffer(I2S_NUM_0);
  return true;
}

static bool startSpeaker() {
  i2s_config_t config={};
  config.mode=static_cast<i2s_mode_t>(I2S_MODE_MASTER|I2S_MODE_TX);
  config.sample_rate=SAMPLE_RATE;
  config.bits_per_sample=I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format=I2S_CHANNEL_FMT_RIGHT_LEFT;
  config.communication_format=I2S_COMM_FORMAT_STAND_I2S;
  config.dma_buf_count=4; config.dma_buf_len=256;
  config.tx_desc_auto_clear=true;
  if (i2s_driver_install(I2S_NUM_1,&config,0,nullptr)!=ESP_OK) return false;
  i2s_pin_config_t pins={};
  pins.mck_io_num=I2S_PIN_NO_CHANGE; pins.bck_io_num=15; pins.ws_io_num=16;
  pins.data_out_num=17; pins.data_in_num=I2S_PIN_NO_CHANGE;
  if (i2s_set_pin(I2S_NUM_1,&pins)!=ESP_OK) {
    i2s_driver_uninstall(I2S_NUM_1); return false;
  }
  i2s_zero_dma_buffer(I2S_NUM_1);
  return true;
}

static void pollButton();

static void handleFrame(uint8_t kind,const uint8_t *payload,uint16_t length) {
  if (kind==FRAME_WELCOME && length==14 && memcmp(payload,"{\"protocol\":1}",14)==0) {
    connected=true; lastHost=millis(); lcdDrawFace(FACE_ID_READY);
  } else if (kind==FRAME_FACE && connected && length==1) {
    lcdDrawFace(listening?FACE_ID_LISTEN:payload[0]);
  } else if (kind==FRAME_THEME && connected && length==1 && payload[0]<=1) {
    /* Legacy 0/1 requests both retain Emotion Ball. */
  } else if (kind==FRAME_ANIMATION && connected && length==1) {
    animationEnabled=payload[0]!=0;
  } else if (kind==FRAME_HEARTBEAT && connected) {
    lastHost=millis();
  } else if (kind==FRAME_DISPLAY && connected && length==2) {
    pendingColor.store(payload[0]|(static_cast<uint16_t>(payload[1])<<8));
  } else if (kind==FRAME_AUDIO_DOWN && connected && speakerReady && !listening && length && length<=1024 && length%2==0) {
    ++receivedAudio;
    if (!playing) { playing=true; lcdDrawFace(FACE_ID_SPEAK); }
    int16_t stereo[1024];
    uint64_t energySum=0;
    size_t count=length/2;
    for (size_t i=0;i<count;++i) {
      int16_t value=static_cast<int16_t>(payload[2*i]|(static_cast<uint16_t>(payload[2*i+1])<<8));
      stereo[2*i]=value; stereo[2*i+1]=value;
      energySum+=static_cast<int64_t>(value)*value;
    }
    speakerEnvelope=fminf(1.f,sqrtf(static_cast<float>(energySum)/count)/1600.f);
    speakerEnvelopeAt=millis();
    size_t written=0;
    i2s_write(I2S_NUM_1,stereo,count*4,&written,pdMS_TO_TICKS(100));
    const uint8_t ok=written==count*4 ? 1 : 0;
    sendFrame(FRAME_ACK,&ok,1);
    ++sentAcks;
  } else if (kind==FRAME_AUDIO_END && playing) {
    playing=false;
    if (!listening) lcdDrawFace(FACE_ID_READY);
  }
}

static void pollHost() {
  const uint32_t started=micros();
  while (Serial.available()) {
    int incoming=Serial.read();
    if (incoming<0) break;
    if (rxLength>=sizeof(rxBuffer)) rxLength=0;
    rxBuffer[rxLength++]=static_cast<uint8_t>(incoming);
    while (rxLength>=2) {
      if (rxBuffer[0]!=0xA5 || rxBuffer[1]!=0x5A) {
        memmove(rxBuffer,rxBuffer+1,--rxLength); continue;
      }
      if (rxLength<9) break;
      uint16_t length=rxBuffer[5]|(static_cast<uint16_t>(rxBuffer[6])<<8);
      if (length>MAX_PAYLOAD) {
        memmove(rxBuffer,rxBuffer+1,--rxLength); continue;
      }
      size_t frameLength=9+length;
      if (rxLength<frameLength) break;
      uint16_t expected=rxBuffer[frameLength-2]|
        (static_cast<uint16_t>(rxBuffer[frameLength-1])<<8);
      bool valid=crcStep(0xFFFF,rxBuffer+2,5+length)==expected;
      if (!valid) ++badCrc;
      if (valid) {
        pollButton(); // Let the button interrupt a stream between audio frames.
        handleFrame(rxBuffer[2],rxBuffer+7,length);
      }
      size_t consumed=valid?frameLength:1;
      rxLength-=consumed;
      memmove(rxBuffer,rxBuffer+consumed,rxLength);
      // A steady audio queue must yield between frames so expressions and
      // button input are serviced even while the speaker DMA is draining.
      if (micros()-started>=6000) return;
    }
  }
}

static void pollButton() {
  static int lastRaw=HIGH,stable=HIGH;
  static uint32_t changedAt=0;
  int raw=digitalRead(KEY_PIN);
  if (raw!=lastRaw) {lastRaw=raw;changedAt=millis();}
  if (raw!=stable && millis()-changedAt>=30) {
    stable=raw;
    if (stable==LOW && connected && micReady) {
      if (playing) {
        playing=false;
        if (speakerReady) i2s_zero_dma_buffer(I2S_NUM_1);
      }
      listening=!listening;
      const uint8_t state=listening?1:0;
      sendFrame(FRAME_BUTTON,&state,1);
      lcdDrawFace(listening?FACE_ID_LISTEN:FACE_ID_THINK);
    }
  }
}

static void pollMicrophone() {
  if (!micReady || !listening || !connected) return;
  int32_t raw[256]; size_t bytes=0;
  if (i2s_read(I2S_NUM_0,raw,sizeof(raw),&bytes,pdMS_TO_TICKS(10))!=ESP_OK) return;
  int16_t mono[128];
  size_t pairs=min(static_cast<size_t>(128),bytes/(sizeof(int32_t)*2));
  for (size_t i=0;i<pairs;++i) {
    int32_t left=raw[2*i]>>16,right=raw[2*i+1]>>16;
    mono[i]=static_cast<int16_t>(abs(left)>=abs(right)?left:right);
  }
  if (pairs) sendFrame(FRAME_AUDIO_UP,reinterpret_cast<const uint8_t *>(mono),pairs*2);
}

void setup() {
  pinMode(KEY_PIN,INPUT_PULLUP);
  Serial.setRxBufferSize(8192);
  Serial.begin(115200);
  micReady=startMicrophone();
  speakerReady=startSpeaker();
  lcdInit();
  currentFace=-1;
  lcdApplyFace(micReady&&speakerReady?FACE_ID_BOOT:FACE_ID_ERROR);
  screenTaskRunning=xTaskCreatePinnedToCore(lcdTask,"screen",6144,nullptr,1,nullptr,0)==pdPASS;
}

void loop() {
  pollHost();
  if (connected && millis()-lastHost>5000) {
    connected=false; listening=false; playing=false; lcdDrawFace(FACE_ID_SLEEP);
  }
  pollButton();
  if (!connected && millis()-lastHello>=2000) {
    lastHello=millis();
      sendJson(FRAME_HELLO,"{\"protocol\":1,\"firmware\":\"voice-device-1.13\"}");
  }
  if (connected && millis()-lastStatus>=3000) {
    lastStatus=millis();
    char status[768];
    snprintf(status,sizeof(status),"{\"listening\":%s,\"playing\":%s,\"speaker_ready\":%s,\"face\":%d,\"frame\":%u,\"uptime_ms\":%lu,\"audio_rx\":%lu,\"audio_ack\":%lu,\"bad_crc\":%lu,\"reset_reason\":%d,\"screen_buffer\":%s,\"compose_us\":%lu,\"push_us\":%lu,\"animation_enabled\":%s,\"presents\":%lu,\"source_updates\":%lu,\"cached_frames\":%u,\"display_theme\":%u,\"ball_bytes\":%lu,\"dirty_tiles\":%u,\"diff_buffer\":%s}",
      listening?"true":"false",playing?"true":"false",speakerReady?"true":"false",currentFace.load(),currentFaceFrame.load(),
      static_cast<unsigned long>(millis()),static_cast<unsigned long>(receivedAudio),
      static_cast<unsigned long>(sentAcks),static_cast<unsigned long>(badCrc),
      static_cast<int>(esp_reset_reason()),lcdFrameBytes?"true":"false",
      static_cast<unsigned long>(lcdComposeUs),static_cast<unsigned long>(lcdPushUs),animationEnabled?"true":"false",
      static_cast<unsigned long>(lcdPresents),static_cast<unsigned long>(lcdSourceUpdates),lcdCachedFrames,displayTheme,static_cast<unsigned long>(qiuqiuPixelBytes.load()),qiuqiuDirtyTiles.load(),qiuqiuPrevious?"true":"false");
    sendJson(FRAME_STATUS,status);
  }
  pollMicrophone();
  if(!screenTaskRunning) lcdService();
}
