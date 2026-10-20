#pragma once
#include <esp32s3/rom/miniz.h>

extern const uint8_t petPack[] asm("_binary_assets_dsh_pet_animations_bin_start");
extern const uint8_t petBackground[] asm("_binary_assets_dsh_pet_background_bin_start");

namespace pet {
constexpr int W=168,N=W*W,FPS=40,X=36,Y=76;
static uint8_t *indices=nullptr,*delta=nullptr;
static uint16_t *last=nullptr,*from=nullptr;
static uint16_t palette[256];
// Optional, bounded PSRAM cache of lossless sparse XOR deltas. Repeated
// animation frames no longer have to inflate zlib data from flash each time.
constexpr uint32_t CACHE_LIMIT=6*1024*1024,MASK_BYTES=N/8;
static uint8_t **deltaCache=nullptr;
static uint32_t clipCacheBytes[13]={},clipCacheUsed[13]={},cacheClock=0;
static std::atomic<uint32_t> cacheBytes{0},cacheHits{0},cacheMisses{0};
static tinfl_decompressor inflaterStorage;
static tinfl_decompressor *inflater=&inflaterStorage;
static uint32_t clipOffset,frameOffset,dataOffset;
static std::atomic<uint32_t> action{0},frame{0},randomCount{0},nextIdle{0},decodeErrors{0};
static std::atomic<uint32_t> decodeUs{0},colorUs{0},blendUs{0};
static std::atomic<bool> internalFrame{false};
static int face=-1,previousRandom=-1;
static uint32_t began=0,transition=0,lastTick=0;
static bool valid=false,backgroundNeeded=true;
static std::atomic<bool> bootGreeting{false};
// Diagnostic modes: 1 hold, 2 repeat frozen pixels, 3 compute animation without writes,
// 4 CPU-only busy work, 5 PSRAM read into internal scratch, 6 internal-RAM copy,
// 7 flash read into internal scratch, 8 decode-only, 9 colors-only, 10 combined load,
// 11 sequential 56 KB write, 12 transposed read, 13 sequential read.
// Modes 4-13 keep the displayed image frozen and never write the LCD.
// 14 plays only idle at the original cadence, without random actions or fades.
// 15 keeps that same motion but sends cost-selected changed 8-row bands.
// 16/17 sample that motion at 30/20 presentations per second; source time stays 40 fps.
// 18/19 present at 50/60 Hz, repeating the last dirty rectangle for duplicate source frames.
// 20 requests 119 Hz presentation for a temporary maximum-scan comparison.
// Normal ANIMATION commands clear this mode; no web control enables it.
static std::atomic<unsigned> testMode{0};
static std::atomic<uint32_t> testHash{0},loadUs{0};
static std::atomic<uint32_t> pixelBytes{0},writeWindows{0};
static bool testCaptured=false;
static bool steadyTest() {const unsigned mode=testMode;return mode>=14&&mode<=20;}
static uint32_t u32(const uint8_t *p) {return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
static void *alloc(size_t n) {return heap_caps_malloc(n,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);}
// Modest software image dimming; BLK remains wired to its existing pull-up.
// Apply once to the palette and background so transitions share the same level.
constexpr unsigned IMAGE_LEVEL=100;
constexpr bool ACTION_CROSSFADE=true; // Restore eased action transitions at user request.
static uint16_t dimColor(uint16_t value) {
  unsigned r=((value>>11)*IMAGE_LEVEL+50)/100;
  unsigned g=(((value>>5)&63)*IMAGE_LEVEL+50)/100;
  unsigned b=((value&31)*IMAGE_LEVEL+50)/100;
  return (r<<11)|(g<<5)|b;
}
static uint16_t backgroundColor(int pixel) {
  const auto p=petBackground+pixel*2;
  return dimColor((uint16_t(p[0])<<8)|p[1]);
}
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
  // Keep the hot decoder state in internal RAM. Removing the two RGB
  // lookahead frames frees their space rather than adding another cache.
  indices=(uint8_t*)heap_caps_malloc(N,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  const bool internalIndices=indices!=nullptr;
  if(!indices)indices=(uint8_t*)alloc(N);
  delta=(uint8_t*)heap_caps_malloc(N,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  // Leave at least 64 KiB available for USB/audio and their runtime buffers.
  if(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)>=N*2+65536)
    last=(uint16_t*)heap_caps_malloc(N*2,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  internalFrame=internalIndices&&last!=nullptr;
  if(!last)last=(uint16_t*)alloc(N*2);
  // The crossfade source is read for every transition pixel. Prefer internal
  // RAM so the fade does not add a PSRAM burst; fall back to PSRAM if needed.
  if(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)>=N*2+65536)
    from=(uint16_t*)heap_caps_malloc(N*2,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  if(!from)from=(uint16_t*)alloc(N*2);

  if(!indices||!delta||!last||!from||!inflater) return false;
  clipOffset=u32(petPack+16);frameOffset=u32(petPack+20);dataOffset=u32(petPack+24);
  deltaCache=(uint8_t**)heap_caps_calloc(u32(petPack+12),sizeof(uint8_t*),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
  memcpy(palette,petPack+28,512);
  for(auto &color:palette)color=__builtin_bswap16(dimColor(color));
  memset(last,0,N*2);valid=true;return true;
}
static bool makeCacheRoom(uint32_t bytes) {
  while(cacheBytes+bytes>CACHE_LIMIT||heap_caps_get_free_size(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)<bytes+512*1024) {
    int victim=-1;
    for(int i=0;i<13;++i)if(i!=int(action.load())&&clipCacheBytes[i]&&
      (victim<0||clipCacheUsed[i]<clipCacheUsed[victim]))victim=i;
    if(victim<0)return false;
    uint32_t first=u32(petPack+clipOffset+victim*8),count=u32(petPack+clipOffset+victim*8+4);
    // Reclaim a small tail batch, preserving the beginning of actions for
    // state transitions. Whole-clip eviction made alternating clips thrash.
    uint32_t released=0;
    for(uint32_t i=first+count;i>first&&released<65536;) {
      auto entry=deltaCache[--i];if(!entry)continue;
      uint16_t packed;memcpy(&packed,entry,2);
      uint32_t size=2+(packed?packed:N);
      free(entry);deltaCache[i]=nullptr;released+=size;
    }
    cacheBytes.fetch_sub(released);clipCacheBytes[victim]-=released;
  }
  return true;
}
static void rememberDelta(uint32_t global,bool absolute) {
  if(!deltaCache)return;
  uint16_t packed=0;
  if(!absolute) {
    // This scratch is separate from delta and indices and will be replaced
    // by colors() before composition. Bound even worst-case dense deltas.
    memset(lcdFrameBytes,0,MASK_BYTES);
    uint32_t end=MASK_BYTES;
    for(int i=0;i<N;++i)if(delta[i]) {
      lcdFrameBytes[i/8]|=1u<<(i%8);
      if(end>=N) {end=N;break;}
      lcdFrameBytes[end++]=delta[i];
    }
    if(end<N)packed=end;
  }
  uint32_t bytes=2+(packed?packed:N);
  if(!makeCacheRoom(bytes))return;
  auto entry=(uint8_t*)alloc(bytes);
  if(!entry)return; // Cache is optional; ordinary decoding remains available.
  memcpy(entry,&packed,2);memcpy(entry+2,packed?lcdFrameBytes:delta,bytes-2);
  deltaCache[global]=entry;cacheBytes.fetch_add(bytes);
  clipCacheBytes[action]+=bytes;clipCacheUsed[action]=++cacheClock;
}
static bool decode(uint32_t global,bool key) {
  uint32_t t=micros();
  auto entry=petPack+frameOffset+global*8;
  uint32_t size=u32(entry+4),offset=u32(entry);
  const bool absolute=key||(size&0x80000000);
  uint16_t packed=0;
  if(deltaCache&&deltaCache[global]) {
    auto entry=deltaCache[global];memcpy(&packed,entry,2);
    memcpy(delta,entry+2,packed?packed:N);
    ++cacheHits;clipCacheUsed[action]=++cacheClock;
  } else {
    ++cacheMisses;
    size_t input=size&0x7fffffff,output=N;
    tinfl_init(inflater);
    auto result=tinfl_decompress(inflater,petPack+dataOffset+offset,&input,delta,delta,&output,
      TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF);
    if(result!=TINFL_STATUS_DONE||output!=N) {++decodeErrors;return false;}
    rememberDelta(global,absolute);
  }
  if(absolute) memcpy(indices,delta,N);
  else if(packed) {
    auto values=delta+MASK_BYTES;
    for(int i=0;i<MASK_BYTES;++i) {
      unsigned bits=delta[i];
      while(bits) {indices[i*8+__builtin_ctz(bits)]^=*values++;bits&=bits-1;}
    }
  }
  else {
    static_assert(N%4==0,"word-wise delta requires complete words");
    auto dst=reinterpret_cast<uint32_t*>(indices);
    auto src=reinterpret_cast<const uint32_t*>(delta);
    for(int i=0;i<N/4;++i)dst[i]^=src[i];
  }
  decodeUs.fetch_add(micros()-t);
  return true;
}
static void colors(uint16_t *dest,const uint16_t *previous=nullptr,unsigned fade=256) {
  uint32_t t=micros();
  // The animation pack is stored in display orientation. Palette conversion is
  // therefore a sequential read; the old runtime 90-degree transpose used a
  // 168-byte column stride that correlated with visible panel flicker.
  // Transition fading is folded into the same pass so the finished frame is
  // written once instead of being read back, blended and rewritten.
  uint16_t row[W];
  for(int py=0;py<W;++py) {
    for(int px=0;px<W;++px) {
      uint16_t value=palette[indices[py*W+px]];
      if(previous&&fade<256) {
        const uint16_t before=previous[py*W+px];
        // Background pixels are identical in every clip. Skipping them avoids
        // most of the per-pixel blend work during the 220 ms transition.
        if(before!=value)
          value=__builtin_bswap16(blend(__builtin_bswap16(before),
                                        __builtin_bswap16(value),fade));
      }
      row[px]=value;
    }
    memcpy(dest+py*W,row,W*2);
  }
  colorUs.fetch_add(micros()-t);
}
static uint32_t count() {return u32(petPack+clipOffset+action*8+4);}
static void seek(uint32_t local) {
  uint32_t first=u32(petPack+clipOffset+action*8),key=local/FPS*FPS;
  for(uint32_t f=key;f<=local;++f) if(!decode(first+f,f==key))return;
  frame=local;
}
static void start(uint32_t id,uint32_t now) {
  if(ACTION_CROSSFADE&&!steadyTest())memcpy(from,last,N*2);
  action=id;began=now;transition=now;seek(0);
}
static void enter(uint32_t now,bool greeting=false) {
  backgroundNeeded=true;face=-1;bootGreeting=greeting;
  nextIdle=now+8000+esp_random()%14001;
}
static int target(int f) {
  if(f==FACE_ID_LISTEN)return 2;
  if(f==FACE_ID_THINK||f==FACE_ID_APPROVE)return 3;
  if(f==FACE_ID_SPEAK)return 4;
  return 0;
}
static void tick(uint32_t now,int current,bool animate,bool force=false) {
  const uint32_t renderStarted=micros();
  if(!init())return;
  static uint32_t cadenceUs=0;
  static unsigned cadenceMode=0;
  const unsigned mode=testMode;
  if(mode==0||(mode>=16&&mode<=20)) {
    const uint32_t period=mode==0?11111:(mode==20?8403:(mode==19?16667:(mode==18?20000:(mode==16?33333:50000)))),currentUs=micros();
    if(cadenceMode!=mode) {cadenceMode=mode;cadenceUs=currentUs;}
    const uint32_t elapsed=currentUs-cadenceUs;
    if(!force&&elapsed<period)return;
    cadenceUs+=elapsed/period*period;
  } else {
    cadenceMode=0;
    if(!force&&now-lastTick<1000/FPS)return;
  }
  lastTick=now;
  decodeUs=0;colorUs=0;
  if(backgroundNeeded) {

    lcdSetWindow(0,0,239,319);lcdBeginPixels();
    for(int y=0;y<320;++y) {
      for(int x=0;x<240;++x) {
        uint16_t value=backgroundColor(y*240+x);
        lcdRowBytes[x*2]=value>>8;lcdRowBytes[x*2+1]=value;
      }
      lcdWritePixels(lcdRowBytes,480);
    }
    lcdEndPixels();
    backgroundNeeded=false;
    // Crossfade the first character from the matching background, never black.
    for(int y=0;y<W;++y)for(int x=0;x<W;++x) {
      int p=(y+Y)*240+x+X;last[y*W+x]=__builtin_bswap16(backgroundColor(p));
    }
  }
  if(current!=face) {
    if(testMode) {testMode=0;animationEnabled=true;}
    // USB ready/sleep notifications must not cut short the power-on greeting.
    // Real work and errors interrupt it immediately; the owner task never waits.
    const bool keepGreeting=bootGreeting&&target(current)==0&&current!=FACE_ID_ERROR;
    face=current;
    if(!keepGreeting)bootGreeting=false;
    const unsigned nextAction=keepGreeting?9:target(current);
    // Different host states can map to the same clip. Keep its timeline and
    // current transition instead of restarting the clip on every notification.
    if(action!=nextAction)start(nextAction,now);
    nextIdle=now+8000+esp_random()%14001;
  }
  // Moving diagnostics do not freeze a pose. Capture afresh only when they
  // switch to a frozen phase, rather than retaining an old moving-frame hash.
  if(!testMode||steadyTest())testCaptured=false;
  if(testMode&&!steadyTest()&&!force) {
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
        memcpy(lcdRowBytes,last+y*W,W*2);lcdWritePixels(lcdRowBytes,W*2);
      }
      lcdEndPixels();++lcdPresents;
      pixelBytes.fetch_add(N*2);++writeWindows;
    }
    if(testMode>=4&&testMode<=7) {
      // Keep the frozen image untouched. Each mode runs a bounded three-millisecond
      // burst per 40 Hz tick so the current draw can be compared across CPU,
      // external-PSRAM, internal-RAM and flash work without any LCD traffic.
      const uint32_t started=micros();
      if(testMode==4) {
        volatile uint32_t value=0x9e3779b9u;
        while(micros()-started<3000) {
          for(int i=0;i<128;++i) value=value*1664525u+1013904223u;
        }
      } else if(testMode==5) {
        do { memcpy(delta,from,N); } while(micros()-started<3000);
      } else if(testMode==6) {
        do { memcpy(lcdFrameBytes,delta,N); } while(micros()-started<3000);
      } else {
        // Walk across the embedded animation pack so the reads miss the small
        // flash cache instead of replaying one cached region.
        static uint32_t loadPosition=0;
        do {
          memcpy(delta,petPack+loadPosition,N);
          loadPosition=(loadPosition+N)%(4u*1024*1024);
        } while(micros()-started<3000);
      }
      loadUs=micros()-started;
      return;
    }
    if(testMode==9) {
      // Output-side work only: palette-convert into the 56 KB final frame and
      // read it back, without decoding or writing the LCD.
      const uint32_t started=micros();
      do { colors(reinterpret_cast<uint16_t*>(lcdFrameBytes)); } while(micros()-started<3000);
      loadUs=micros()-started;
      return;
    }
    if(testMode==10) {
      // Combined burst: CPU arithmetic plus PSRAM read/write, internal copy and
      // flash read in the same 3 ms window.
      const uint32_t started=micros();
      static uint32_t loadPosition=0;
      volatile uint32_t value=0x9e3779b9u;
      do {
        for(int i=0;i<64;++i) value=value*1664525u+1013904223u;
        memcpy(delta,from,N);
        memcpy(from,delta,N);
        memcpy(lcdFrameBytes,delta,N);
        memcpy(delta,petPack+loadPosition,N);
        loadPosition=(loadPosition+N)%(4u*1024*1024);
      } while(micros()-started<3000);
      loadUs=micros()-started;
      return;
    }
    if(testMode==11) {
      // Sequential 56 KB write into the final frame buffer: isolates write volume
      // from the transposed read pattern used by colors().
      const uint32_t started=micros();
      do {
        auto out=reinterpret_cast<uint32_t*>(lcdFrameBytes);
        for(int i=0;i<N/2;++i) out[i]=uint32_t(i)*2654435761u;
      } while(micros()-started<3000);
      loadUs=micros()-started;
      return;
    }
    if(testMode==12) {
      // The exact column-wise read pattern of colors(), without any writes.
      const uint32_t started=micros();
      volatile uint32_t sum=0;
      do {
        for(int py=0;py<W;++py)
          for(int px=0;px<W;++px) sum+=indices[px*W+(W-1-py)];
      } while(micros()-started<3000);
      loadUs=micros()-started;
      return;
    }
    if(testMode==13) {
      // Sequential 28 KB read control for testMode 12.
      const uint32_t started=micros();
      volatile uint32_t sum=0;
      do {
        for(int i=0;i<N;++i) sum+=indices[i];
      } while(micros()-started<3000);
      loadUs=micros()-started;
      return;
    }
    if(testMode<=2)return;
  }
  if(!animate&&!force)return;
  if(steadyTest()&&(action!=0||bootGreeting)) {
    bootGreeting=false;start(0,now);
  }
  if(animate) {
    uint32_t duration=count()*1000/FPS;
    if(now-began>=duration) {
      if(action>=5) {bootGreeting=false;start(0,now);nextIdle=now+8000+esp_random()%14001;}
      else {
        // A loop is not a change of action. Carry the clock remainder forward
        // and seek the keyframe without recapturing a fade on every loop.
        began+=(now-began)/duration*duration;
        seek(0);
      }
    }
    if(!steadyTest()&&target(face)==0&&action==0&&int32_t(now-nextIdle)>=0) {
      int id;do{id=5+esp_random()%8;}while(id==previousRandom);
      previousRandom=id;++randomCount;start(id,now);
    }
    uint32_t wanted=((now-began)*FPS/1000)%count();
    if(wanted!=frame) {
      uint32_t first=u32(petPack+clipOffset+action*8);
      uint32_t old=frame.load(),steps=(wanted+count()-old)%count();
      if(steps<=FPS) {
        // State now belongs to the displayed source frame, not a lookahead.
        // Replay only the required deltas; missed frames keep real-time timing.
        for(uint32_t i=1;i<=steps;++i) {
          uint32_t local=(old+i)%count();decode(first+local,local==0);
        }
        frame=wanted;
      } else seek(wanted);
    }
  }
  if(testMode==8) {
    // Decode-only: advance the real animation and build index state, then stop
    // before palette conversion, dirty scan, shadow copy and LCD output.
    loadUs=micros()-renderStarted;
    return;
  }
  const unsigned linearFade=(!ACTION_CROSSFADE||steadyTest())?256:min(256u,(now-transition)*256/220);
  // Ease the real action transition at both ends. Blend opaque, complete
  // source/target images; never fade via black, white or a cleared background.
  const unsigned fade=(linearFade*linearFade*(768-2*linearFade)+32768)>>16;
  uint32_t blendStarted=micros();
  colors(reinterpret_cast<uint16_t*>(lcdFrameBytes),ACTION_CROSSFADE?from:nullptr,fade);
  if(fade<256)blendUs=micros()-blendStarted;
  lcdComposeUs=micros()-renderStarted;
  const uint32_t pushStarted=micros();
  // Find the final dirty rectangle in internal row scratch. One RAMWR stream
  // avoids a patchwork of separately addressed old/new tiles during scanout.
  int left=W,right=-1,top=W,bottom=-1;
  int16_t rowLeft[W],rowRight[W];
  uint16_t oldRow[W];
  for(int y=0;y<W;++y) {
    rowLeft[y]=W;rowRight[y]=-1;
    memcpy(oldRow,last+y*W,W*2);
    auto current=reinterpret_cast<const uint16_t*>(lcdFrameBytes)+y*W;
    if(memcmp(oldRow,current,W*2)==0)continue;
    int lo=0,hi=W-1;
    while(oldRow[lo]==current[lo])++lo;
    while(oldRow[hi]==current[hi])--hi;
    rowLeft[y]=lo;rowRight[y]=hi;
    left=min(left,lo);right=max(right,hi);top=min(top,y);bottom=y;
  }
  // Keep source timing at 40 fps. At 50/60 Hz some source frames repeat;
  // resend valid final pixels without clearing or advancing the clip early.
  static int repeatLeft=0,repeatTop=0,repeatRight=W-1,repeatBottom=W-1;
  if(mode==0||(mode>=18&&mode<=20)) {
    if(right>=left) {repeatLeft=left;repeatTop=top;repeatRight=right;repeatBottom=bottom;}
    else {left=repeatLeft;top=repeatTop;right=repeatRight;bottom=repeatBottom;}
  }
  if(right>=left&&testMode!=3) {
    // The shared buffer is sized for Emotion Ball (192 square), leaving room
    // after this 168-square image for a packed 16-row internal transfer strip.
    constexpr int ROWS=16;
    static_assert(N*2+W*ROWS*2<=192*192*2,"transfer scratch exceeds shared buffer");
    auto strip=lcdFrameBytes+N*2;
    auto push=[&](int l,int t,int r,int b) {
      const int bytes=(r-l+1)*2;
      lcdSetWindow(X+l,Y+t,X+r,Y+b);lcdBeginPixels();
      for(int y=t;y<=b;y+=ROWS) {
        int rows=min(ROWS,b-y+1);
        for(int row=0;row<rows;++row)memcpy(strip+row*bytes,lcdFrameBytes+((y+row)*W+l)*2,bytes);
        lcdWritePixels(strip,rows*bytes);
      }
      lcdEndPixels();pixelBytes.fetch_add((r-l+1)*(b-t+1)*2);++writeWindows;
    };
    struct Band {uint8_t left,top,right,bottom;};
    Band bands[(W+7)/8];int bandCount=0,bandPixels=0;
    if(testMode==15) {
      for(int y=0;y<W;y+=8) {
        int l=W,r=-1,t=W,b=-1;
        for(int row=y;row<min(W,y+8);++row)if(rowRight[row]>=0) {
          l=min(l,int(rowLeft[row]));r=max(r,int(rowRight[row]));t=min(t,row);b=row;
        }
        if(r>=l) {
          bands[bandCount++]={uint8_t(l),uint8_t(t),uint8_t(r),uint8_t(b)};
          bandPixels+=(r-l+1)*(b-t+1);
        }
      }
    }
    // Allow a small per-window overhead; fall back to one rectangle when
    // splitting would cost more than the pixels it avoids. Never clear first.
    if(bandCount&&bandPixels+bandCount*32<(right-left+1)*(bottom-top+1)+32) {
      for(int i=0;i<bandCount;++i)push(bands[i].left,bands[i].top,bands[i].right,bands[i].bottom);
    } else push(left,top,right,bottom);
  }

  if(testMode!=3)memcpy(last,lcdFrameBytes,N*2);
  lcdPushUs=micros()-pushStarted;
  if(testMode!=3)++lcdPresents;
  ++lcdSourceUpdates;
}
}
