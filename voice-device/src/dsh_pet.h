#pragma once
#include <esp32s3/rom/miniz.h>

extern const uint8_t petPack[] asm("_binary_assets_dsh_pet_animations_bin_start");
extern const uint8_t petBackground[] asm("_binary_assets_dsh_pet_background_bin_start");

namespace pet {
constexpr int W=192,N=W*W;
static uint8_t *indices=nullptr,*delta=nullptr;
static uint16_t *a=nullptr,*b=nullptr,*last=nullptr,*from=nullptr;
static tinfl_decompressor inflaterStorage;
static tinfl_decompressor *inflater=&inflaterStorage;
static uint32_t clipOffset,frameOffset,dataOffset;
static std::atomic<uint32_t> action{0},frame{0},randomCount{0},nextIdle{0},decodeErrors{0};
static int face=-1,previousRandom=-1;
static uint32_t began=0,transition=0,lastTick=0;
static bool valid=false,backgroundNeeded=true;
static uint32_t u32(const uint8_t *p) {return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
static void *alloc(size_t n) {return heap_caps_malloc(n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);}
static uint16_t blend(uint16_t x,uint16_t y,unsigned t) {
  unsigned s=256-t;
  return (((((x>>11)&31)*s+((y>>11)&31)*t)>>8)<<11)|
         (((((x>>5)&63)*s+((y>>5)&63)*t)>>8)<<5)|(((x&31)*s+(y&31)*t)>>8);
}
static bool init() {
  if(valid) return true;

  if(memcmp(petPack,"DSP1",4)) return false;
  indices=(uint8_t*)alloc(N);
  delta=(uint8_t*)heap_caps_malloc(N,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  a=(uint16_t*)alloc(N*2);b=(uint16_t*)alloc(N*2);
  last=(uint16_t*)alloc(N*2);from=(uint16_t*)alloc(N*2);

  if(!indices||!delta||!a||!b||!last||!from||!inflater) return false;
  clipOffset=u32(petPack+16);frameOffset=u32(petPack+20);dataOffset=u32(petPack+24);
  memset(last,0,N*2);valid=true;return true;
}
static bool decode(uint32_t global,bool key) {
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
  return true;
}
static void colors(uint16_t *dest) {
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
}
static uint32_t count() {return u32(petPack+clipOffset+action*8+4);}
static void seek(uint32_t local) {
  uint32_t first=u32(petPack+clipOffset+action*8),key=local/24*24;
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
  if(!force&&now-lastTick<20)return;
  lastTick=now;
  if(backgroundNeeded) {

    lcdSetWindow(0,0,239,319);lcdBeginPixels();
    for(int y=0;y<320;++y) {memcpy(lcdRowBytes,petBackground+y*480,480);SPI.writeBytes(lcdRowBytes,480);}
    lcdEndPixels();
    backgroundNeeded=false;
    // Crossfade the first character from the matching background, never black.
    for(int y=0;y<W;++y)for(int x=0;x<W;++x) {
      int p=((y+64)*240+x+24)*2;last[y*W+x]=petBackground[p]|(uint16_t(petBackground[p+1])<<8);
    }
  }
  if(current!=face) {
    face=current;start(target(current),now);
    nextIdle=now+8000+esp_random()%14001;
  }
  if(!animate&&!force)return;
  if(animate) {
    uint32_t duration=count()*1000/24;
    if(now-began>=duration) {
      if(action>=5) {start(0,now);nextIdle=now+8000+esp_random()%14001;}
      else start(action==0&&esp_random()%3==0?1:action==1?0:action.load(),now);
    }
    if(target(face)==0&&action<2&&int32_t(now-nextIdle)>=0) {
      int id;do{id=5+esp_random()%8;}while(id==previousRandom);
      previousRandom=id;++randomCount;start(id,now);
    }
    uint32_t wanted=((now-began)*24/1000)%count();
    if(wanted!=frame) {
      uint32_t first=u32(petPack+clipOffset+action*8);
      uint32_t old=frame.load(),steps=(wanted+count()-old)%count();
      if(steps<=24) {
        if(steps==1) memcpy(a,b,N*2);
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
  unsigned fraction=animate?((now-began)*24%1000)*256/1000:0;
  unsigned fade=min(256u,(now-transition)*256/220);
  uint16_t ar[W],br[W],fr[W],out[W];
  for(int y=0;y<W;++y) {
    memcpy(ar,a+y*W,W*2);memcpy(br,b+y*W,W*2);memcpy(fr,from+y*W,W*2);
    for(int x=0;x<W;++x) {
      uint16_t c=blend(__builtin_bswap16(ar[x]),__builtin_bswap16(br[x]),fraction);
      if(fade<256)c=blend(__builtin_bswap16(fr[x]),c,fade);
      out[x]=__builtin_bswap16(c);
    }
    memcpy(lcdFrameBytes+y*W*2,out,W*2);
  }
  lcdComposeUs=micros()-renderStarted;
  const uint32_t pushStarted=micros();
  // Final opaque tiles only: no clearing pass, no empty intermediate frame.
  for(int y=0;y<W;y+=8) for(int x=0;x<W;) {
    auto changed=[&](int xx) {
      for(int yy=y;yy<y+8;++yy)
        if(memcmp(reinterpret_cast<uint8_t*>(last)+(yy*W+xx)*2,lcdFrameBytes+(yy*W+xx)*2,16))return true;
      return false;
    };
    if(!changed(x)){x+=8;continue;}
    int left=x;do{x+=8;}while(x<W&&changed(x));
    lcdSetWindow(24+left,64+y,24+x-1,64+y+7);lcdBeginPixels();
    for(int yy=y;yy<y+8;++yy) SPI.writeBytes(lcdFrameBytes+(yy*W+left)*2,(x-left)*2);
    lcdEndPixels();
  }

  memcpy(last,lcdFrameBytes,N*2);
  lcdPushUs=micros()-pushStarted;
  ++lcdPresents;++lcdSourceUpdates;
}
}
