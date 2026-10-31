#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
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
static constexpr uint8_t FRAME_THEME=14, FRAME_SCREEN_TEST=15;
static constexpr uint8_t FRAME_WAKE_CONFIG=21,FRAME_WAKE_AUDIO=22,FRAME_CAPTURE_CONTROL=23;
static constexpr uint8_t FRAME_STEREO_UP=24,FRAME_STEREO_WAKE=25;
static constexpr uint8_t FRAME_OPEN_BRIDGE=26;
static bool wakeStreaming=false,captureAutomatic=false,captureJustStarted=false;
static uint8_t microphoneMode=0,microphoneSlot=0;
static uint32_t microphoneSelectedAt=0;
static std::atomic<uint8_t> displayTheme{2};
static std::atomic<int> pendingTheme{-1};
static std::atomic<int> pendingFace{-1},pendingColor{-1};
static constexpr uint8_t LCD_NORMAL_SCAN=0x05; // ST7789 nominal 90 Hz (FRCTRL2).
static bool screenTaskRunning=false;
static std::atomic<int> pendingLcdScan{-1};
static std::atomic<uint32_t> pendingLcdHz{0},lcdBusHz{40000000};
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
static std::atomic<uint32_t> lcdPresents{0},lcdSourceUpdates{0},lcdPixelWrites{0};

static uint16_t crcStep(uint16_t crc, const uint8_t *data, size_t length) {
  for (size_t i=0; i<length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (int bit=0; bit<8; ++bit)
      crc = crc & 0x8000 ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

static Preferences networkPrefs;
static WebSocketsClient deviceSocket;
static String networkSsid,networkPassword,networkHost,networkToken,networkHeaders;
static uint16_t networkPort=8788;
static bool socketStarted=false,networkSelected=false;
static uint32_t wifiAttempt=0,lastUsbFrame=0,wifiStableAt=0;
static bool wifiSafeMode=false,wifiRestoredCpu=false;
static std::atomic<unsigned> wifiDisconnectReason{0};
static uint8_t networkRx[8192];
static size_t networkRead=0,networkWrite=0;
static void resetLink() {
  connected=false; listening=false; playing=false; rxLength=0;
  wakeStreaming=false;captureAutomatic=false;
  networkRead=networkWrite=0;
  if(speakerReady)i2s_zero_dma_buffer(I2S_NUM_1);
  lastHello=0;
}

static void sendFrame(uint8_t kind, const uint8_t *payload=nullptr, uint16_t length=0) {
  if (length>MAX_PAYLOAD || (!networkSelected && !Serial)) return;
  uint8_t header[7]={0xA5,0x5A,kind,
    static_cast<uint8_t>(txSequence),static_cast<uint8_t>(txSequence>>8),
    static_cast<uint8_t>(length),static_cast<uint8_t>(length>>8)};
  ++txSequence;
  uint16_t crc=crcStep(0xFFFF,header+2,5);
  if (length) crc=crcStep(crc,payload,length);
  uint8_t trailer[2]={static_cast<uint8_t>(crc),static_cast<uint8_t>(crc>>8)};
  if(networkSelected) {
    if(!deviceSocket.isConnected())return;
    uint8_t frame[9+MAX_PAYLOAD];
    memcpy(frame,header,7);if(length)memcpy(frame+7,payload,length);
    memcpy(frame+7+length,trailer,2);
    if(!deviceSocket.sendBIN(frame,length+9))resetLink();
  } else {
    Serial.write(header,sizeof(header));
    if (length) Serial.write(payload,length);
    Serial.write(trailer,sizeof(trailer));
  }
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

// All window state and SPI calls belong to the display task (setup runs first).
// Stage the window, then send CASET/RASET/RAMWR and its payload under one CS.
static int lcdWindow[4]={0,0,LCD_WIDTH-1,LCD_HEIGHT-1};
static bool lcdWindowValid=true,lcdPixelsOpen=false;
static size_t lcdExpectedBytes=0,lcdWrittenBytes=0;
static std::atomic<uint32_t> lcdTxErrors{0};
static void lcdSetWindow(int x0,int y0,int x1,int y1) {
  lcdWindowValid=x0>=0&&y0>=0&&x1>=x0&&y1>=y0&&x1<LCD_WIDTH&&y1<LCD_HEIGHT;
  if(!lcdWindowValid) {++lcdTxErrors;return;}
  lcdWindow[0]=x0;lcdWindow[1]=y0;lcdWindow[2]=x1;lcdWindow[3]=y1;
}
static void lcdBeginPixels() {
  if(!lcdWindowValid||lcdPixelsOpen) {++lcdTxErrors;return;}
  lcdExpectedBytes=size_t(lcdWindow[2]-lcdWindow[0]+1)*(lcdWindow[3]-lcdWindow[1]+1)*2;
  lcdWrittenBytes=0;
  SPI.beginTransaction(lcdSpi);digitalWrite(LCD_CS,LOW);
  digitalWrite(LCD_DC,LOW);SPI.transfer(0x2A);digitalWrite(LCD_DC,HIGH);
  SPI.transfer(lcdWindow[0]>>8);SPI.transfer(lcdWindow[0]);
  SPI.transfer(lcdWindow[2]>>8);SPI.transfer(lcdWindow[2]);
  digitalWrite(LCD_DC,LOW);SPI.transfer(0x2B);digitalWrite(LCD_DC,HIGH);
  SPI.transfer(lcdWindow[1]>>8);SPI.transfer(lcdWindow[1]);
  SPI.transfer(lcdWindow[3]>>8);SPI.transfer(lcdWindow[3]);
  digitalWrite(LCD_DC,LOW);SPI.transfer(0x2C);digitalWrite(LCD_DC,HIGH);
  lcdPixelsOpen=true;++lcdPixelWrites;
}
static void lcdWritePixels(const uint8_t *data,size_t bytes) {
  if(!lcdPixelsOpen||!data||(bytes&1)||bytes>lcdExpectedBytes-lcdWrittenBytes) {
    ++lcdTxErrors;return;
  }
  SPI.writeBytes(data,bytes); // Blocking Arduino HAL: source may be reused only after this returns.
  lcdWrittenBytes+=bytes;
}
static void lcdEndPixels() {
  if(!lcdPixelsOpen) {++lcdTxErrors;return;}
  if(lcdWrittenBytes!=lcdExpectedBytes)++lcdTxErrors;
  digitalWrite(LCD_CS,HIGH);SPI.endTransaction();lcdPixelsOpen=false;
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
  for (int y=y0;y<=y1;++y) lcdWritePixels(lcdRowBytes,width*2);
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
      lcdWritePixels(lcdFrameBytes+(row*192+x)*2,width*2);
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

#include "dsh_pet.h"

static void lcdApplyFace(int index) {
  if (index<0 || index>=FACE_COUNT || index==currentFace) return;
  currentFace=index;
  currentFaceFrame=0;
  if(displayTheme==2) pet::tick(millis(),index,animationEnabled,true); else lcdDrawQiuqiu();
}

static void lcdTickAnimation() {
  if(displayTheme==2) {pet::tick(millis(),currentFace,animationEnabled);return;}
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

// SPI and all composition have one owner. Keep this task on the USB/I2S
// core: the cross-core PSRAM composition path reset the device during audio.
static void lcdService() {
  int theme=pendingTheme.exchange(-1);
  if(theme>=1 && theme<=2 && theme!=displayTheme) {
    // Keep the 40 MHz bus while using the selected 90 Hz scan/presentation target.
    lcdBusHz=40000000;
    lcdSpi=SPISettings(lcdBusHz.load(),MSBFIRST,SPI_MODE0);
    const uint8_t scan=LCD_NORMAL_SCAN; // Selected normal scan; highest-scan mode remains diagnostic.
    lcdCommand(0xC6,&scan,1);
    displayTheme=theme;
    if(theme==2)pet::enter(millis());
    else {lcdFill(0x0843);qiuqiuNeedsFull=true;qiuqiuPreviousValid=false;lcdDrawQiuqiu();}
  }
  uint32_t clock=pendingLcdHz.exchange(0);
  if(clock) {lcdBusHz=clock;lcdSpi=SPISettings(clock,MSBFIRST,SPI_MODE0);}
  int scan=pendingLcdScan.exchange(-1);
  if(scan>=0) {const uint8_t value=scan;lcdCommand(0xC6,&value,1);}
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
  lcdCommand(0xC6,&LCD_NORMAL_SCAN,1);
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

static void setListening(bool enabled,bool automatic=false,bool cancelled=false) {
  if(enabled && playing) {
    playing=false;
    if(speakerReady)i2s_zero_dma_buffer(I2S_NUM_1);
  }
  listening=enabled;captureAutomatic=enabled&&automatic;captureJustStarted=enabled;
  const uint8_t state=enabled?1:(cancelled?2:0);
  sendFrame(FRAME_BUTTON,&state,1);
  lcdDrawFace(enabled?FACE_ID_LISTEN:(cancelled?FACE_ID_READY:FACE_ID_THINK));
}

static void handleFrame(uint8_t kind,const uint8_t *payload,uint16_t length) {
  if(kind==18 && !networkSelected && !listening && !playing && length<=1 && (!length || payload[0]<=1)) {
    const unsigned profile=length?payload[0]:0;
    const bool animated=animationEnabled.load(),micWasReady=micReady,speakerWasReady=speakerReady;
    const uint32_t cpuMHz=getCpuFrequencyMhz();
    char starting[80];snprintf(starting,sizeof(starting),"{\"phase\":\"starting\",\"profile\":%u}",profile);
    sendJson(19,starting);Serial.flush();delay(25);
    networkPrefs.putBool("starting",true);
    if(profile==1) {
      animationEnabled=false;delay(100);
      if(micReady){i2s_driver_uninstall(I2S_NUM_0);micReady=false;}
      if(speakerReady){i2s_driver_uninstall(I2S_NUM_1);speakerReady=false;}
      for(int pin:{4,5,15,16,17}){pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
      sendJson(19,"{\"phase\":\"i2s_stopped\"}");Serial.flush();delay(25);
      setCpuFrequencyMhz(80);delay(100);
      sendJson(19,"{\"phase\":\"cpu_low_ready\"}");Serial.flush();delay(25);
    }
    const uint32_t freeBefore=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    sendJson(19,"{\"phase\":\"before_radio_init\"}");Serial.flush();delay(25);
    bool modeStarted=WiFi.mode(WIFI_STA);
    sendJson(19,modeStarted?"{\"phase\":\"mode_ready\"}":"{\"phase\":\"mode_failed\"}");
    WiFi.setTxPower(WIFI_POWER_8_5dBm);
    int count=modeStarted?WiFi.scanNetworks(false,true,true,120):-100;
    bool targetVisible=false;
    for(int i=0;i<count;i++)if(WiFi.SSID(i)==networkSsid)targetVisible=true;
    WiFi.scanDelete();
    if(modeStarted && targetVisible) {
      WiFi.begin(networkSsid.c_str(),networkPassword.c_str());
      uint32_t began=millis();
      while(WiFi.status()!=WL_CONNECTED && millis()-began<8000)delay(100);
    }
    JsonDocument report;
    report["phase"]="complete";report["profile"]=profile;report["mode_started"]=modeStarted;
    report["scan_count"]=count;report["target_visible"]=targetVisible;
    report["wifi_status"]=(int)WiFi.status();report["disconnect_reason"]=wifiDisconnectReason.load();
    report["connected"]=WiFi.status()==WL_CONNECTED;
    report["ip"]=WiFi.localIP().toString();report["free_before"]=freeBefore;
    report["free_after"]=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    report["phase"]="radio_complete";
    char radioResult[768];size_t radioBytes=serializeJson(report,radioResult,sizeof(radioResult));
    if(radioBytes<sizeof(radioResult))sendFrame(19,reinterpret_cast<uint8_t*>(radioResult),radioBytes);
    WiFi.disconnect(true);networkPrefs.putBool("starting",false);
    if(profile==1){
      setCpuFrequencyMhz(cpuMHz);
      if(micWasReady)micReady=startMicrophone();
      if(speakerWasReady)speakerReady=startSpeaker();
    }
    animationEnabled=animated;lastHost=lastUsbFrame=millis();
    report["phase"]="complete";report["mic_restored"]=micReady;report["speaker_restored"]=speakerReady;
    char result[1024];size_t n=serializeJson(report,result,sizeof(result));
    if(n<sizeof(result))sendFrame(19,reinterpret_cast<uint8_t*>(result),n);
  } else if(kind==16 && !networkSelected && !listening && !playing) {
    JsonDocument config;
    bool ok=!deserializeJson(config,payload,length);
    String ssid=config["ssid"] | "",password=config["password"] | "";
    String host=config["host"] | "",token=config["token"] | "";
    int port=config["port"] | 8788;
    IPAddress address;
    ok=ok && ssid.length()>0 && ssid.length()<=32 && password.length()<=63
      && address.fromString(host) && token.length()>=32 && token.length()<=128
      && port>=1024 && port<=65535;
    if(ok) {
      networkPrefs.putBool("safe",false);networkPrefs.putBool("starting",false);
      ok=networkPrefs.putString("ssid",ssid)>0 && networkPrefs.putString("pass",password)==password.length()
        && networkPrefs.putString("host",host)>0 && networkPrefs.putString("token",token)>0
        && networkPrefs.putUShort("port",port)>0;
    }
    const uint8_t result=ok?1:0;sendFrame(17,&result,1);
    if(ok){delay(100);ESP.restart();}
  } else if(kind==FRAME_WAKE_CONFIG && connected && length==2 && payload[0]<=1 && payload[1]<=3) {
    wakeStreaming=payload[0]!=0;microphoneMode=payload[1];
    if(!wakeStreaming && captureAutomatic && listening)setListening(false,false,true);
    sendFrame(FRAME_WAKE_CONFIG,payload,2);
  } else if(kind==FRAME_CAPTURE_CONTROL && connected && micReady && length==1 && payload[0]<=2) {
    if(payload[0]==1) {
      if(wakeStreaming && !playing && !listening)setListening(true,true);
    } else if(listening && captureAutomatic) {
      setListening(false,false,payload[0]==2);
    }
  } else if (kind==FRAME_WELCOME && length==14 && memcmp(payload,"{\"protocol\":1}",14)==0) {
    connected=true; lastHost=millis(); lcdDrawFace(FACE_ID_READY);
  } else if (kind==FRAME_FACE && connected && length==1) {
    lcdDrawFace(listening?FACE_ID_LISTEN:payload[0]);
  } else if (kind==FRAME_THEME && connected && length==1 && payload[0]<=2) {
    pendingTheme=payload[0]==2?2:1;
  } else if (kind==FRAME_SCREEN_TEST && connected && (length==1||(length==2&&payload[1]<=2)) && payload[0]<=20
             && displayTheme==2 && !playing && !listening) {
    pendingLcdHz=length==2&&payload[1]==1?20000000:length==2&&payload[1]==2?40000000:26666666;
    pendingLcdScan=payload[0]==20?0x00:(payload[0]==0?LCD_NORMAL_SCAN:0x0F);
    pet::testMode=payload[0];animationEnabled=payload[0]==0||payload[0]==3||payload[0]==8||payload[0]>=14;
  } else if (kind==FRAME_ANIMATION && connected && length==1) {
    pendingLcdHz=40000000;pendingLcdScan=LCD_NORMAL_SCAN;
    pet::testMode=0;animationEnabled=payload[0]!=0;
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
  while (networkSelected ? networkRead!=networkWrite : Serial.available()>0) {
    int incoming=networkSelected ? networkRx[(networkRead++)%sizeof(networkRx)] : Serial.read();
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
        if(!networkSelected)lastUsbFrame=millis();
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
  static constexpr uint32_t HOLD_MS=3000;
  static int lastRaw=HIGH,stable=HIGH;
  static uint32_t changedAt=0,pressedAt=0;
  static bool longSent=false;
  int raw=digitalRead(KEY_PIN);
  if (raw!=lastRaw) {lastRaw=raw;changedAt=millis();}
  if (raw!=stable && millis()-changedAt>=30) {
    stable=raw;
    if (stable==LOW) {
      pressedAt=millis(); longSent=false;
    } else if (!longSent && millis()-pressedAt<HOLD_MS && connected && micReady) {
      setListening(!listening);
    }
  }
  if (stable==LOW && raw==LOW && !longSent && millis()-pressedAt>=HOLD_MS) {
    longSent=true;
    // The USB standby listener can start Bridge before its protocol handshake.
    const uint8_t action=1; sendFrame(FRAME_OPEN_BRIDGE,&action,1);
  }
}

static void pollMicrophone() {
  if (!micReady || !connected || playing || (!listening && !wakeStreaming)) return;
  int32_t raw[256]; size_t bytes=0;
  if (i2s_read(I2S_NUM_0,raw,sizeof(raw),&bytes,pdMS_TO_TICKS(10))!=ESP_OK) return;
  int16_t mono[128];
  size_t pairs=min(static_cast<size_t>(128),bytes/(sizeof(int32_t)*2));
  uint64_t energy[2]={0,0};
  for(size_t i=0;i<pairs;i++)for(int ch=0;ch<2;ch++) {
    int64_t sample=raw[2*i+ch]>>16;energy[ch]+=sample*sample;
  }
  if(microphoneMode==3) {
    int16_t stereo[256];
    for(size_t i=0;i<pairs*2;i++)stereo[i]=static_cast<int16_t>(raw[i]>>16);
    captureJustStarted=false;
    if(pairs)sendFrame(listening?FRAME_STEREO_UP:FRAME_STEREO_WAKE,
      reinterpret_cast<const uint8_t*>(stereo),pairs*4);
    return;
  }
  if(microphoneMode)microphoneSlot=microphoneMode-1;
  else if(captureJustStarted || (!listening && millis()-microphoneSelectedAt>=1000)) {
    uint8_t other=1-microphoneSlot;
    if((captureJustStarted && energy[other]>energy[microphoneSlot])
       || energy[other]>energy[microphoneSlot]*4)microphoneSlot=other;
    microphoneSelectedAt=millis();
  }
  captureJustStarted=false;
  for (size_t i=0;i<pairs;++i) {
    // Select one whole channel, never splice two microphones sample by sample.
    mono[i]=static_cast<int16_t>(raw[2*i+microphoneSlot]>>16);
  }
  if (pairs) sendFrame(listening?FRAME_AUDIO_UP:FRAME_WAKE_AUDIO,reinterpret_cast<const uint8_t *>(mono),pairs*2);
}

static void pollNetwork() {
  const bool usbActive=Serial.available()>0 || (lastUsbFrame && millis()-lastUsbFrame<5000);
  bool selected=millis()>30000 && !usbActive && !wifiSafeMode && !networkSsid.isEmpty();
  if(selected!=networkSelected) {
    resetLink();networkSelected=selected;
    if(!selected && socketStarted){deviceSocket.disconnect();WiFi.disconnect(true);socketStarted=false;setCpuFrequencyMhz(240);wifiStableAt=0;wifiRestoredCpu=false;}
  }
  if(!networkSelected)return;
  if(!socketStarted) {
    networkPrefs.putBool("starting",true);
    bool animated=animationEnabled.exchange(false);setCpuFrequencyMhz(80);delay(100);
    WiFi.mode(WIFI_STA);WiFi.setTxPower(WIFI_POWER_8_5dBm);WiFi.setSleep(false);
    WiFi.begin(networkSsid.c_str(),networkPassword.c_str());wifiAttempt=millis();
    networkHeaders="Authorization: Bearer "+networkToken;
    deviceSocket.begin(networkHost,networkPort,"/device");
    deviceSocket.setExtraHeaders(networkHeaders.c_str());
    deviceSocket.setReconnectInterval(3000);
    deviceSocket.onEvent([](WStype_t type,uint8_t *data,size_t length){
      if(type==WStype_DISCONNECTED || type==WStype_CONNECTED)resetLink();
      if(type==WStype_BIN) {
        if(length>sizeof(networkRx)-(networkWrite-networkRead)){deviceSocket.disconnect();resetLink();return;}
        for(size_t i=0;i<length;i++)networkRx[(networkWrite++)%sizeof(networkRx)]=data[i];
      }
    });
    socketStarted=true;animationEnabled=animated;
  }
  if(WiFi.status()==WL_CONNECTED) {
    if(!wifiStableAt)wifiStableAt=millis();
    if(!wifiRestoredCpu && millis()-wifiStableAt>10000){setCpuFrequencyMhz(240);wifiRestoredCpu=true;}
    if(connected && millis()-wifiStableAt>30000 && networkPrefs.getBool("starting",false))networkPrefs.putBool("starting",false);
    deviceSocket.loop();
  }
  else if(millis()-wifiAttempt>15000){WiFi.reconnect();wifiAttempt=millis();}
}

void setup() {
  pinMode(KEY_PIN,INPUT_PULLUP);
  Serial.setRxBufferSize(8192);
  Serial.begin(115200);
  WiFi.onEvent([](WiFiEvent_t event,WiFiEventInfo_t info){
    if(event==ARDUINO_EVENT_WIFI_STA_DISCONNECTED)wifiDisconnectReason=info.wifi_sta_disconnected.reason;
  });
  networkPrefs.begin("bridge-net",false);
  wifiSafeMode=networkPrefs.getBool("safe",false);
  if(esp_reset_reason()==ESP_RST_BROWNOUT && networkPrefs.getBool("starting",false)) {
    wifiSafeMode=true;networkPrefs.putBool("safe",true);networkPrefs.putBool("starting",false);
  }
  networkSsid=networkPrefs.getString("ssid","");networkPassword=networkPrefs.getString("pass","");
  networkHost=networkPrefs.getString("host","");networkToken=networkPrefs.getString("token","");
  networkPort=networkPrefs.getUShort("port",8788);
  // USB remains usable even if the configured wireless network is unavailable.
  micReady=startMicrophone();
  speakerReady=startSpeaker();
  lcdInit();
  pet::enter(millis(),true);
  currentFace=-1;
  lcdApplyFace(micReady&&speakerReady?FACE_ID_BOOT:FACE_ID_ERROR);
  screenTaskRunning=xTaskCreatePinnedToCore(lcdTask,"screen",16384,nullptr,1,nullptr,1)==pdPASS;
}

void loop() {
  pollNetwork();
  pollHost();
  if (connected && millis()-lastHost>5000) {
    connected=false; listening=false; playing=false; lcdDrawFace(FACE_ID_SLEEP);
  }
  pollButton();
  if (!connected && millis()-lastHello>=2000) {
    lastHello=millis();
      char hello[256];
      snprintf(hello,sizeof(hello),"{\"protocol\":1,\"firmware\":\"voice-device-1.65\",\"wake_protocol\":1,\"stereo_protocol\":1,\"display_theme\":%u,\"animation_enabled\":%s,\"boot_animation\":%s,\"pet_action\":%lu,\"pet_frame\":%lu,\"presents\":%lu,\"uptime_ms\":%lu}",
        displayTheme.load(),animationEnabled?"true":"false",pet::bootGreeting?"true":"false",
        (unsigned long)pet::action.load(),(unsigned long)pet::frame.load(),(unsigned long)lcdPresents.load(),(unsigned long)millis());
      sendJson(FRAME_HELLO,hello);
  }
  if (connected && millis()-lastStatus>=3000) {
    lastStatus=millis();
    char status[1280];
    snprintf(status,sizeof(status),"{\"listening\":%s,\"playing\":%s,\"speaker_ready\":%s,\"face\":%d,\"frame\":%u,\"uptime_ms\":%lu,\"audio_rx\":%lu,\"audio_ack\":%lu,\"bad_crc\":%lu,\"reset_reason\":%d,\"screen_buffer\":%s,\"compose_us\":%lu,\"push_us\":%lu,\"animation_enabled\":%s,\"presents\":%lu,\"source_updates\":%lu,\"cached_frames\":%u,\"display_theme\":%u,\"ball_bytes\":%lu,\"dirty_tiles\":%u,\"diff_buffer\":%s}",
      listening?"true":"false",playing?"true":"false",speakerReady?"true":"false",currentFace.load(),currentFaceFrame.load(),
      static_cast<unsigned long>(millis()),static_cast<unsigned long>(receivedAudio),
      static_cast<unsigned long>(sentAcks),static_cast<unsigned long>(badCrc),
      static_cast<int>(esp_reset_reason()),lcdFrameBytes?"true":"false",
      static_cast<unsigned long>(lcdComposeUs),static_cast<unsigned long>(lcdPushUs),animationEnabled?"true":"false",
      static_cast<unsigned long>(lcdPresents),static_cast<unsigned long>(lcdSourceUpdates),lcdCachedFrames,displayTheme.load(),static_cast<unsigned long>(qiuqiuPixelBytes.load()),qiuqiuDirtyTiles.load(),qiuqiuPrevious?"true":"false");
    size_t used=strlen(status);
    snprintf(status+used-1,sizeof(status)-used+1,",\"pet_action\":%lu,\"pet_frame\":%lu,\"pet_random_count\":%lu,\"pet_decode_errors\":%lu,\"pet_decode_us\":%lu,\"pet_color_us\":%lu,\"pet_blend_us\":%lu,\"pet_internal_frames\":%u,\"screen_test\":%u,\"screen_test_hash\":%lu,\"pet_load_us\":%lu,\"pixel_writes\":%lu,\"lcd_spi_hz\":%lu}",
      (unsigned long)pet::action.load(),(unsigned long)pet::frame.load(),(unsigned long)pet::randomCount.load(),(unsigned long)pet::decodeErrors.load(),(unsigned long)pet::decodeUs.load(),(unsigned long)pet::colorUs.load(),(unsigned long)pet::blendUs.load(),pet::internalFrame.load()?1u:0u,pet::testMode.load(),(unsigned long)pet::testHash.load(),(unsigned long)pet::loadUs.load(),(unsigned long)lcdPixelWrites.load(),(unsigned long)lcdBusHz.load());
    used=strlen(status);
    snprintf(status+used-1,sizeof(status)-used+1,",\"pet_cache_bytes\":%lu,\"pet_cache_hits\":%lu,\"pet_cache_misses\":%lu}",
      (unsigned long)pet::cacheBytes.load(),(unsigned long)pet::cacheHits.load(),(unsigned long)pet::cacheMisses.load());
    used=strlen(status);
    snprintf(status+used-1,sizeof(status)-used+1,",\"pet_pixel_bytes\":%lu,\"pet_windows\":%lu,\"lcd_tx_errors\":%lu}",
      (unsigned long)pet::pixelBytes.load(),(unsigned long)pet::writeWindows.load(),(unsigned long)lcdTxErrors.load());
    used=strlen(status);
    snprintf(status+used-1,sizeof(status)-used+1,",\"transport\":\"%s\",\"wifi_rssi\":%d,\"free_internal\":%lu}",
      networkSelected?"wifi":"usb",WiFi.status()==WL_CONNECTED?WiFi.RSSI():0,
      (unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    sendJson(FRAME_STATUS,status);
    char networkStatus[256];
    snprintf(networkStatus,sizeof(networkStatus),"{\"wifi_safe_mode\":%s,\"wifi_configured\":%s,\"wifi_selected\":%s,\"wifi_status\":%d,\"wifi_disconnect_reason\":%u,\"free_internal\":%lu}",
      wifiSafeMode?"true":"false",networkSsid.isEmpty()?"false":"true",networkSelected?"true":"false",(int)WiFi.status(),
      wifiDisconnectReason.load(),(unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    sendJson(20,networkStatus);
  }
  pollMicrophone();
  if(!screenTaskRunning) lcdService();
  // Yield idle polling time to the display task on this core. Audio RX/ACK
  // and microphone DMA remain serviced at millisecond cadence.
  delay(1);
}
