#pragma once
#include <esp32s3/rom/miniz.h>

extern const uint8_t petPack[] asm("_binary_assets_dsh_pet_animations_bin_start");
extern const uint8_t petBackground[] asm("_binary_assets_dsh_pet_background_bin_start");

namespace pet {
constexpr int W=168,N=W*W,FPS=40,X=36,Y=76;
static uint8_t *indices=nullptr,*delta=nullptr;
static uint16_t *a=nullptr,*b=nullptr,*last=nullptr,*from=nullptr;
static tinfl_decompressor inflaterStorage;
static tinfl_decompressor *inflater=&inflaterStorage;
static uint32_t clipOffset,frameOffset,dataOffset;
static std::atomic<uint32_t> action{0},frame{0},randomCount{0},nextIdle{0},decodeErrors{0};
static std::atomic<uint32_t> decodeUs{0},colorUs{0},blendUs{0};
static std::atomic<bool> internalFrame{false};
static int face=-1,previousRandom=-1;
static uint32_t began=0,transition=0,lastTick=0;
static bool valid=false,backgroundNeeded=true;
// Diagnostic modes: 1 hold, 2 repeat frozen pixels, 3 compute animation without writes.
// Normal ANIMATION commands clear this mode; no web control enables it.
static std::atomic<unsigned> testMode{0};
static std::atomic<uint32_t> testHash{0};
static bool testCaptured=false;
static uint32_t u32(const uint8_t *p) {return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
static void *alloc(size_t n) {return heap_caps_malloc(n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);}
static inline uint16_t blend(uint16_t x,uint16_t y,unsigned t) {
  if(x==y)return x;
  // Separate green into the high halfword; padding prevents channel carries.
  // Five-bit interpolation keeps exact endpoints and identical backgrounds.
  const uint32_t mask=0x07e0f81f;
  uint32_t a=(uint32_t(x)|(uint32_t(x)<<16))&mask;
  uint32_t b=(uint32_t(y)|(uint32_t(y)<<16))&mask;
  unsigned alpha=(t+4)>>3;
  uint32_t c=((a*(32-alpha)+b*alpha)>>5)&mask;
  return uint16_t(c|(c>>16));
}
static bool init() {
  if(valid) return true;

  if(memcmp(petPack,"DSP1",4)||petPack[4]!=W||petPack[6]!=W||petPack[8]!=FPS) return false;
  indices=(uint8_t*)alloc(N);
  delta=(uint8_t*)heap_caps_malloc(N,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  a=(uint16_t*)heap_caps_malloc(N*2,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  internalFrame=a!=nullptr;
  if(!a)a=(uint16_t*)alloc(N*2);
  b=(uint16_t*)alloc(N*2);
  last=(uint16_t*)alloc(N*2);from=(uint16_t*)alloc(N*2);

  if(!indices||!delta||!a||!b||!last||!from||!inflater) return false;
  clipOffset=u32(petPack+16);frameOffset=u32(petPack+20);dataOffset=u32(petPack+24);
  memset(last,0,N*2);valid=true;return true;
}
static bool decode(uint32_t global,bool key) {
  uint32_t t=micros();
  auto entry=petPack+frameOffset+global*8;
  uint32_t size=u32(entry+4),offset=u32(entry);
  size_t input=size&0x7fffffff,output=N;
  tinfl_init(inflater);
  auto result=tinfl_decompress(inflater,petPack+dataOffset+offset,&input,delta,delta,&output,
    TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
  if(result!=TINFL_STATUS_DONE||output!=N) {++decodeErrors;return false;}
  if(key||(size&0x80000000)) memcpy(indices,delta,N);
  else {
    uint8_t row[W];
    for(int y=0;y<W;++y) {
      memcpy(row,indices+y*W,W);
      for(int x=0;x<W;++x)row[x]^=delta[y*W+x];
      memcpy(indices+y*W,row,W);
    }
  }
  decodeUs.fetch_add(micros()-t);
  return true;
}
static void colors(uint16_t *dest) {
  uint32_t t=micros();
  // Reuse the internal composition buffer as indexed scratch before rendering.
  // Contiguous PSRAM row writes avoid the original transpose cache misses.
  memcpy(lcdFrameBytes,indices,N);
  uint16_t palette[256],row[W];
  memcpy(palette,petPack+28,512);
  for(int i=0;i<256;++i)palette[i]=__builtin_bswap16(palette[i]);
  for(int py=0;py<W;++py) {
    for(int px=0;px<W;++px)row[px]=palette[lcdFrameBytes[px*W+(W-1-py)]];
    memcpy(dest+py*W,row,W*2);
  }
  colorUs.fetch_add(micros()-t);
}
static uint32_t count() {return u32(petPack+clipOffset+action*8+4);}
static void seek(uint32_t local) {
  uint32_t first=u32(petPack+clipOffset+action*8),key=local/FPS*FPS;
  for(uint32_t f=key;f<=local;++f) if(!decode(first+f,f==key))return;
  colors(a);frame=local;
  // Keep delta decoding state at the upcoming frame. Normal playback advances
  // sequentially; missed deadlines seek from a bounded one-second keyframe.
  uint32_t next=(local+1)%count();
  if(next==0) decode(first,true);else decode(first+next,false);
  colors(b);
}
static void start(uint32_t id,uint32_t now) {
  memcpy(from,last,N*2);action=id;began=now;transition=now;seek(0);
}
static void enter(uint32_t now) {backgroundNeeded=true;face=-1;nextIdle=now+8000+esp_random()%14001;}
static int target(int f) {
  if(f==FACE_ID_LISTEN)return 2;
  if(f==FACE_ID_THINK||f==FACE_ID_APPROVE)return 3;
  if(f==FACE_ID_SPEAK)return 4;
  return 0;
}
static void tick(uint32_t now,int current,bool animate,bool force=false) {
  const uint32_t renderStarted=micros();
  if(!init())return;
  if(!force&&now-lastTick<1000/FPS)return;
  lastTick=now;
  decodeUs=0;colorUs=0;
  if(backgroundNeeded) {

    lcdSetWindow(0,0,239,319);lcdBeginPixels();
    for(int y=0;y<320;++y) {memcpy(lcdRowBytes,petBackground+y*480,480);SPI.writeBytes(lcdRowBytes,480);}
    lcdEndPixels();
    backgroundNeeded=false;
    // Crossfade the first character from the matching background, never black.
    for(int y=0;y<W;++y)for(int x=0;x<W;++x) {
      int p=((y+Y)*240+x+X)*2;last[y*W+x]=petBackground[p]|(uint16_t(petBackground[p+1])<<8);
    }
  }
  if(current!=face) {
    if(testMode) {testMode=0;animationEnabled=true;}
    face=current;start(target(current),now);
    nextIdle=now+8000+esp_random()%14001;
  }
  if(!testMode)testCaptured=false;
  if(testMode&&!force) {
    if(!testCaptured) {
      uint8_t row[W*2];uint32_t hash=2166136261u;
      for(int y=0;y<W;++y) {
        memcpy(row,last+y*W,W*2);
        for(auto value:row)hash=(hash^value)*16777619u;
      }
      testHash=hash;testCaptured=true;
    }
    if(testMode==2) {
      lcdSetWindow(X,Y,X+W-1,Y+W-1);lcdBeginPixels();
      for(int y=0;y<W;++y) {
        memcpy(lcdRowBytes,last+y*W,W*2);SPI.writeBytes(lcdRowBytes,W*2);
      }
      lcdEndPixels();++lcdPresents;
    }
    if(testMode<=2)return;
  }
  if(!animate&&!force)return;
  if(animate) {
    uint32_t duration=count()*1000/FPS;
    if(now-began>=duration) {
      if(action>=5) {start(0,now);nextIdle=now+8000+esp_random()%14001;}
      else start(action==0&&esp_random()%3==0?1:action==1?0:action.load(),now);
    }
    if(target(face)==0&&action<2&&int32_t(now-nextIdle)>=0) {
      int id;do{id=5+esp_random()%8;}while(id==previousRandom);
      previousRandom=id;++randomCount;start(id,now);
    }
    uint32_t wanted=((now-began)*FPS/1000)%count();
    if(wanted!=frame) {
      uint32_t first=u32(petPack+clipOffset+action*8);
      uint32_t old=frame.load(),steps=(wanted+count()-old)%count();
      if(steps<=FPS) {
        if(steps==1) {auto previous=a;a=b;b=previous;}
        else {
          // The decoder already contains old+1 (the lookahead frame). Replay
          // only skipped deltas, never restart from a distant keyframe.
          for(uint32_t i=2;i<=steps;++i) {
            uint32_t local=(old+i)%count();decode(first+local,local==0);
          }
          colors(a);
        }
        frame=wanted;
        uint32_t next=(wanted+1)%count();decode(first+next,next==0);colors(b);
      } else seek(wanted);
    }
  }
  uint32_t blendStarted=micros();
  unsigned fade=min(256u,(now-transition)*256/220);
  // Normal playback copies a complete precomputed motion frame. Only state
  // changes blend against the last displayed image, avoiding empty frames.
  if(fade>=256)memcpy(lcdFrameBytes,a,N*2);
  else {
    uint16_t ar[W],fr[W],out[W];
    for(int y=0;y<W;++y) {
      memcpy(ar,a+y*W,W*2);memcpy(fr,from+y*W,W*2);
      for(int x=0;x<W;++x)
        out[x]=__builtin_bswap16(blend(__builtin_bswap16(fr[x]),__builtin_bswap16(ar[x]),fade));
      memcpy(lcdFrameBytes+y*W*2,out,W*2);
    }
  }
  blendUs=micros()-blendStarted;
  lcdComposeUs=micros()-renderStarted;
  const uint32_t pushStarted=micros();
  // Find the final dirty rectangle in internal row scratch. One RAMWR stream
  // avoids a patchwork of separately addressed old/new tiles during scanout.
  int left=W,right=-1,top=W,bottom=-1;
  uint16_t oldRow[W];
  for(int y=0;y<W;++y) {
    memcpy(oldRow,last+y*W,W*2);
    auto current=reinterpret_cast<const uint16_t*>(lcdFrameBytes)+y*W;
    for(int x=0;x<W;++x)if(oldRow[x]!=current[x]) {
      left=min(left,x);right=max(right,x);top=min(top,y);bottom=y;
    }
  }
  if(right>=left&&testMode!=3) {
    // The shared buffer is sized for Emotion Ball (192 square), leaving room
    // after this 168-square image for a packed 16-row internal transfer strip.
    constexpr int ROWS=16;
    static_assert(N*2+W*ROWS*2<=192*192*2,"transfer scratch exceeds shared buffer");
    auto strip=lcdFrameBytes+N*2;
    const int bytes=(right-left+1)*2;
    lcdSetWindow(X+left,Y+top,X+right,Y+bottom);lcdBeginPixels();
    for(int y=top;y<=bottom;y+=ROWS) {
      int rows=min(ROWS,bottom-y+1);
      for(int r=0;r<rows;++r)memcpy(strip+r*bytes,lcdFrameBytes+((y+r)*W+left)*2,bytes);
      SPI.writeBytes(strip,rows*bytes);
    }
    lcdEndPixels();
  }

  if(testMode!=3)memcpy(last,lcdFrameBytes,N*2);
  lcdPushUs=micros()-pushStarted;
  if(testMode!=3)++lcdPresents;
  ++lcdSourceUpdates;
}
}
