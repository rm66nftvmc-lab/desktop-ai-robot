#include <Arduino.h>
#include <SPI.h>
#include <driver/i2s.h>
#include <esp_system.h>
#include <esp_heap_caps.h>
#include <rom/miniz.h>

#include "faces.h"
#include "screen_assets.h"
#include "qiuqiu_assets.h"
#include <math.h>

// USB CDC: A5 5A | type | seq LE | length LE | payload | CRC16-CCITT LE.
static constexpr uint8_t FRAME_STATUS=1, FRAME_DISPLAY=2, FRAME_AUDIO_UP=3, FRAME_AUDIO_DOWN=4;
static constexpr uint8_t FRAME_HEARTBEAT=5, FRAME_BUTTON=6, FRAME_ACK=8;
static constexpr uint8_t FRAME_HELLO=9, FRAME_WELCOME=10, FRAME_AUDIO_END=11, FRAME_FACE=12;
static constexpr uint8_t FRAME_ANIMATION=13;
static constexpr uint8_t FRAME_THEME=14;
static uint8_t displayTheme=0;
static constexpr uint16_t MAX_PAYLOAD=1024;
static constexpr int KEY_PIN=1, SAMPLE_RATE=16000;
static constexpr int LCD_CS=8, LCD_DC=9, LCD_RST=10, LCD_MOSI=11, LCD_SCLK=12;
static constexpr int LCD_WIDTH=240, LCD_HEIGHT=320;
static_assert(LCD_WIDTH==SCREEN_BG_WIDTH && LCD_HEIGHT==SCREEN_BG_HEIGHT,
              "LCD and generated background dimensions must match");
static SPISettings lcdSpi(40000000, MSBFIRST, SPI_MODE0);
static bool micReady=false, speakerReady=false, connected=false, listening=false, playing=false;
static uint16_t txSequence=0;
static uint32_t lastHost=0, lastHello=0, lastStatus=0;
static uint32_t receivedAudio=0, sentAcks=0, badCrc=0;
static uint8_t rxBuffer[9+MAX_PAYLOAD];
static size_t rxLength=0;
static uint8_t lcdRowBytes[LCD_WIDTH*2];
static uint8_t currentFaceFrame=0;
static bool animationEnabled=true;
static uint8_t *lcdFrameBytes=nullptr;
// The decoder's Huffman tables exceed Arduino's default 8 KB loop stack.
static tinfl_decompressor lcdInflater;
static uint8_t *lcdFrameCache[FACE_COUNT][SCREEN_ANIMATION_FRAME_COUNT]={};
static uint16_t lcdCachedFrames=0;
static uint32_t lcdComposeUs=0,lcdPushUs=0;
static ScreenDirtyRect lcdCachedRect={0,0,0,0};
static size_t lcdCachedLength=0;
static uint32_t lcdPresents=0,lcdSourceUpdates=0;
static uint8_t currentFaceRepeat=0;
static uint32_t lastFaceFrameAt=0;
static constexpr uint32_t FACE_FRAME_INTERVAL_MS=45;
static constexpr uint8_t FACE_FRAME_REPEATS=3;
static_assert(FACE_FRAME_INTERVAL_MS%FACE_FRAME_REPEATS==0,"Repeat slots must divide source-frame duration");
static constexpr uint32_t FACE_REFRESH_INTERVAL_MS=FACE_FRAME_INTERVAL_MS/FACE_FRAME_REPEATS;

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

// The pet's expressions live in flash as run-length encoded RGB565
// (see scripts/build_faces.py), so they survive a power cut and need no network.
static int currentFace=-1;

static void lcdDrawBackground() {
  lcdSetWindow(0,0,LCD_WIDTH-1,LCD_HEIGHT-1);
  lcdBeginPixels();
  for (int y=0;y<LCD_HEIGHT;++y) {
    for (int x=0;x<LCD_WIDTH;++x) {
      uint16_t color=pgm_read_word(&SCREEN_BACKGROUND[y*LCD_WIDTH+x]);
      lcdRowBytes[x*2]=color>>8;
      lcdRowBytes[x*2+1]=color&0xFF;
    }
    SPI.writeBytes(lcdRowBytes,sizeof(lcdRowBytes));
  }
  lcdEndPixels();
}

static void lcdPresentCachedFrame() {
  if (!lcdFrameBytes || !lcdCachedLength) return;
  const int top=(LCD_HEIGHT-FACE_PIXELS)/2;
  lcdSetWindow(lcdCachedRect.x0,top+lcdCachedRect.y0,
               lcdCachedRect.x1,top+lcdCachedRect.y1);
  const uint32_t pushStarted=micros();
  lcdBeginPixels();
  SPI.writeBytes(lcdFrameBytes,lcdCachedLength);
  lcdEndPixels();
  lcdPushUs=micros()-pushStarted;
  ++lcdPresents;
}

// A complete opaque frame is composed before any SPI write. No blank frame.
// Eyes move continuously at 30 Hz; no repeated GIF poses or runtime allocation.
static void lcdDrawQiuqiu() {
  if (!lcdFrameBytes) return;
  const uint32_t started=micros();
  const float t=millis()*.001f;
  for (int y=0;y<192;++y) for (int x=0;x<192;++x) {
    uint16_t color=pgm_read_word(&QIUQIU_TEXTURE[y*192+x]);
    // Match the original asset's counterclockwise screen orientation.
    const int offset=((191-x)*192+y)*2;
    lcdFrameBytes[offset]=color>>8; lcdFrameBytes[offset+1]=color;
  }
  float phase=fmodf(t,4.6f);
  float blink=phase<.22f ? fabsf(phase-.11f)/.11f : 1.f;
  if (currentFace==FACE_ID_SLEEP) blink=.12f;
  const float gazeX=sinf(t*.73f)*3.5f;
  const float gazeY=sinf(t*1.2f)*1.8f;
  for (int eye=0;eye<2;++eye) {
    float cx=(eye?118.f:76.f)+gazeX;
    float cy=(eye?83.f:91.f)+gazeY;
    float half=(eye?10.f:13.f)*blink;
    float radius=eye?4.f:5.f;
    if (currentFace==FACE_ID_LISTEN) half*=1.2f;
    if (currentFace==FACE_ID_SPEAK) half*=.8f+.2f*sinf(t*9.f);
    if (currentFace==FACE_ID_THINK) cy+=sinf(t*3.f+eye)*2.f;
    if (currentFace==FACE_ID_ERROR) half=4;
    const float tilt=eye?-.18f:-.25f;
    for (int y=int(cy-half-radius-7);y<=int(cy+half+radius+7);++y)
      for (int x=int(cx-radius-10);x<=int(cx+radius+10);++x) {
        if (x<0||x>=192||y<0||y>=192) continue;
        float dx=x-cx,dy=y-cy;
        float u=dx-tilt*dy,v=dy+tilt*dx;
        float q=fmaxf(0.f,fabsf(v)-half);
        float coverage=fminf(1.f,fmaxf(0.f,radius+.5f-sqrtf(u*u+q*q)));
        if (coverage<=0) continue;
        int offset=((191-x)*192+y)*2;
        uint16_t bg=(lcdFrameBytes[offset]<<8)|lcdFrameBytes[offset+1];
        uint16_t fg=currentFace==FACE_ID_ERROR?0x8828:0x2125;
        int r=((bg>>11)&31)*(1-coverage)+((fg>>11)&31)*coverage;
        int g=((bg>>5)&63)*(1-coverage)+((fg>>5)&63)*coverage;
        int b=(bg&31)*(1-coverage)+(fg&31)*coverage;
        uint16_t color=(r<<11)|(g<<5)|b;
        lcdFrameBytes[offset]=color>>8; lcdFrameBytes[offset+1]=color;
      }
  }
  lcdComposeUs=micros()-started;
  lcdCachedLength=192*192*2;
  ++lcdSourceUpdates;
  const uint32_t pushStarted=micros();
  lcdSetWindow(24,64,215,255);
  lcdBeginPixels(); SPI.writeBytes(lcdFrameBytes,lcdCachedLength); lcdEndPixels();
  lcdPushUs=micros()-pushStarted;
  ++lcdPresents; ++currentFaceFrame;
}

static bool lcdDecodeFrame(const ScreenCompressedFrame &frame,uint8_t *output) {
  size_t inputBytes=frame.size,decoded=LCD_WIDTH*FACE_PIXELS*2;
  tinfl_init(&lcdInflater);
  const tinfl_status result=tinfl_decompress(&lcdInflater,frame.data,&inputBytes,
    output,output,&decoded,TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
  return result==TINFL_STATUS_DONE && decoded==LCD_WIDTH*FACE_PIXELS*2;
}

static void lcdWarmFrameCache() {
  // Cache animated poses once at boot; playback never needs to allocate.
  // 64 poses occupy 7,372,800 bytes of this board's 8 MB PSRAM.
  for (int index=0;index<FACE_COUNT;++index) {
    ScreenFaceFrames face;
    memcpy_P(&face,&SCREEN_FACES[index],sizeof(face));
    if (face.count<2) continue;
    for (uint8_t frame=0;frame<face.count;++frame) {
      auto *pixels=static_cast<uint8_t *>(heap_caps_malloc(LCD_WIDTH*FACE_PIXELS*2,
        MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
      if (!pixels) return; // Uncached poses retain the decoding fallback.
      if (!lcdDecodeFrame(face.frame[frame],pixels)) {free(pixels);continue;}
      lcdFrameCache[index][frame]=pixels;
      ++lcdCachedFrames;
    }
  }
}

static uint8_t lcdDrawFaceFrame(int index,uint8_t frameIndex,bool partial=false) {
  if (index<0 || index>=FACE_COUNT) return 1;
  ScreenFaceFrames face;
  memcpy_P(&face,&SCREEN_FACES[index],sizeof(face));
  if (!face.count) return 1;
  if (frameIndex>=face.count) frameIndex=0;
  const ScreenCompressedFrame &frame=face.frame[frameIndex];
  if (!frame.data) return face.count;

  const int top=(LCD_HEIGHT-FACE_PIXELS)/2;
  if (top<0) return face.count;
  int x0=0,y0=0,x1=LCD_WIDTH-1,y1=FACE_PIXELS-1;
  if (partial) {
    const ScreenDirtyRect &dirty=frame.dirty;
    x0=dirty.x0; y0=dirty.y0; x1=dirty.x1; y1=dirty.y1;
  }
  // Decode the complete precomposited frame before touching the LCD.
  if (!lcdFrameBytes) return face.count;
  const uint32_t composeStarted=micros();
  const int rowBytes=(x1-x0+1)*2;

  const uint8_t *pixels=lcdFrameCache[index][frameIndex];
  if (!pixels) {
    if (!lcdDecodeFrame(frame,lcdFrameBytes)) {
      lcdCachedLength=0;
      return face.count; // Retain the LCD's last valid image.
    }
    pixels=lcdFrameBytes;
  }
  for (int y=y0;y<=y1;++y)
    memmove(lcdFrameBytes+(y-y0)*rowBytes,
            pixels+(y*LCD_WIDTH+x0)*2,rowBytes);
  lcdComposeUs=micros()-composeStarted;
  lcdCachedRect={static_cast<uint8_t>(x0),static_cast<uint8_t>(y0),
                 static_cast<uint8_t>(x1),static_cast<uint8_t>(y1)};
  lcdCachedLength=rowBytes*(y1-y0+1);
  ++lcdSourceUpdates;
  lcdPresentCachedFrame();
  return face.count;
}

static void lcdDrawFace(int index) {
  if (index<0 || index>=FACE_COUNT || index==currentFace) return;
  currentFace=index;
  currentFaceFrame=0;
  currentFaceRepeat=0;
  if (displayTheme==1) lcdDrawQiuqiu();
  else lcdDrawFaceFrame(currentFace,currentFaceFrame);
  lastFaceFrameAt=millis();
}

static void lcdTickAnimation() {
  const uint32_t elapsed=millis()-lastFaceFrameAt;
  if (displayTheme==1) {
    // Recording keeps the display still to prioritize microphone samples.
    if (!animationEnabled || listening || elapsed<33) return;
    lastFaceFrameAt+=elapsed/33*33;
    lcdDrawQiuqiu();
    return;
  }
  if (!animationEnabled || currentFace<0 || elapsed<FACE_REFRESH_INTERVAL_MS) return;
  ScreenFaceFrames face;
  memcpy_P(&face,&SCREEN_FACES[currentFace],sizeof(face));
  if (face.count<2) return;
  // Anchor to the clock rather than adding draw time to every interval.
  // Each interpolated pose lasts 45 ms with three presentations.
  // Four poses retain the original 180 ms source interval.
  const uint32_t slots=elapsed/FACE_REFRESH_INTERVAL_MS;
  lastFaceFrameAt+=slots*FACE_REFRESH_INTERVAL_MS;
  const uint32_t advances=(currentFaceRepeat+slots)/FACE_FRAME_REPEATS;
  currentFaceRepeat=(currentFaceRepeat+slots)%FACE_FRAME_REPEATS;
  if (advances) {
    currentFaceFrame=(currentFaceFrame+advances)%face.count;
    // Dirty bounds describe adjacent frames only. A late/skipped pose must
    // repaint the full region to avoid leaving pixels from an older pose.
    lcdDrawFaceFrame(currentFace,currentFaceFrame,advances==1);
  } else {
    lcdPresentCachedFrame();
  }
}

static void lcdInit() {
  const size_t frameBytes=LCD_WIDTH*FACE_PIXELS*2;
  lcdFrameBytes=static_cast<uint8_t *>(heap_caps_malloc(frameBytes,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
  if (!lcdFrameBytes)
    lcdFrameBytes=static_cast<uint8_t *>(heap_caps_malloc(frameBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  lcdWarmFrameCache();
  pinMode(LCD_CS,OUTPUT); pinMode(LCD_DC,OUTPUT); pinMode(LCD_RST,OUTPUT);
  digitalWrite(LCD_CS,HIGH); digitalWrite(LCD_DC,HIGH); digitalWrite(LCD_RST,HIGH);
  SPI.begin(LCD_SCLK,-1,LCD_MOSI,LCD_CS);
  digitalWrite(LCD_RST,LOW); delay(20); digitalWrite(LCD_RST,HIGH); delay(120);
  lcdCommand(0x01); delay(150); lcdCommand(0x11); delay(120);
  const uint8_t rgb565=0x55, orientation=0;
  lcdCommand(0x3A,&rgb565,1); lcdCommand(0x36,&orientation,1);
  lcdCommand(0x21); lcdCommand(0x13); delay(10); lcdCommand(0x29); delay(100);
  lcdDrawBackground();
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
    lcdDrawFace(payload[0]);
  } else if (kind==FRAME_THEME && connected && length==1 && payload[0]<=1) {
    if (displayTheme!=payload[0]) {
      displayTheme=payload[0];
      if (displayTheme==1) lcdFill(0x0843); else lcdDrawBackground();
      int face=currentFace; currentFace=-1; lcdDrawFace(face);
    }
  } else if (kind==FRAME_ANIMATION && connected && length==1) {
    animationEnabled=payload[0]!=0;
    lastFaceFrameAt=millis();
  } else if (kind==FRAME_HEARTBEAT && connected) {
    lastHost=millis();
  } else if (kind==FRAME_DISPLAY && connected && length==2) {
    lcdFill(payload[0]|(static_cast<uint16_t>(payload[1])<<8));
  } else if (kind==FRAME_AUDIO_DOWN && connected && speakerReady && !listening && length && length<=1024 && length%2==0) {
    ++receivedAudio;
    if (!playing) { playing=true; lcdDrawFace(FACE_ID_SPEAK); }
    int16_t stereo[1024];
    size_t count=length/2;
    for (size_t i=0;i<count;++i) {
      int16_t value=static_cast<int16_t>(payload[2*i]|(static_cast<uint16_t>(payload[2*i+1])<<8));
      stereo[2*i]=value; stereo[2*i+1]=value;
    }
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
      lcdDrawFace(listening?FACE_ID_LISTEN:FACE_ID_READY);
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
  lcdDrawFace(micReady&&speakerReady?FACE_ID_BOOT:FACE_ID_ERROR);
}

void loop() {
  pollHost();
  if (connected && millis()-lastHost>5000) {
    connected=false; listening=false; playing=false; lcdDrawFace(FACE_ID_SLEEP);
  }
  pollButton();
  if (!connected && millis()-lastHello>=2000) {
    lastHello=millis();
      sendJson(FRAME_HELLO,"{\"protocol\":1,\"firmware\":\"voice-device-1.9\"}");
  }
  if (connected && millis()-lastStatus>=3000) {
    lastStatus=millis();
    char status[512];
    snprintf(status,sizeof(status),"{\"listening\":%s,\"playing\":%s,\"speaker_ready\":%s,\"face\":%d,\"frame\":%u,\"uptime_ms\":%lu,\"audio_rx\":%lu,\"audio_ack\":%lu,\"bad_crc\":%lu,\"reset_reason\":%d,\"screen_buffer\":%s,\"compose_us\":%lu,\"push_us\":%lu,\"animation_enabled\":%s,\"presents\":%lu,\"source_updates\":%lu,\"cached_frames\":%u,\"display_theme\":%u}",
      listening?"true":"false",playing?"true":"false",speakerReady?"true":"false",currentFace,currentFaceFrame,
      static_cast<unsigned long>(millis()),static_cast<unsigned long>(receivedAudio),
      static_cast<unsigned long>(sentAcks),static_cast<unsigned long>(badCrc),
      static_cast<int>(esp_reset_reason()),lcdFrameBytes?"true":"false",
      static_cast<unsigned long>(lcdComposeUs),static_cast<unsigned long>(lcdPushUs),animationEnabled?"true":"false",
      static_cast<unsigned long>(lcdPresents),static_cast<unsigned long>(lcdSourceUpdates),lcdCachedFrames,displayTheme);
    sendJson(FRAME_STATUS,status);
  }
  pollMicrophone();
  lcdTickAnimation();
}
