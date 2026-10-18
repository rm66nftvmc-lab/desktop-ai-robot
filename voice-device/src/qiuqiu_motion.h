#pragma once
#include <math.h>
#include <stdint.h>

namespace qiuqiu {
enum class Mood {Idle, Listen, Think, Speak, Sleep, Approve, Error};
struct Eye {float x,y,half,radius,tilt;};
struct Pose {Eye eyes[2]; float mouth,dots[3];};

inline Pose target(Mood mood,uint32_t now,float energy) {
  float t=now*.001f;
  float phase=fmodf(t,4.6f);
  float blink=phase<.22f ? .5f+.5f*cosf(phase*28.55993f) : 1.f;
  Pose p={{{76+sinf(t*.73f)*3.5f,91+sinf(t*1.2f)*1.8f,13*blink,5,-.25f},
           {118+sinf(t*.73f)*3.5f,83+sinf(t*1.2f)*1.8f,10*blink,4,-.18f}},0,{0,0,0}};
  if (mood==Mood::Listen) {
    // Alert, symmetric eyes facing the person speaking.
    p.eyes[0]={76,87+sinf(t*2)*.7f,12*blink,7,-.08f};
    p.eyes[1]={118,87+sinf(t*2)*.7f,12*blink,7,.08f};
  } else if (mood==Mood::Think || mood==Mood::Approve) {
    // Upward gaze and an asymmetric squint, plus three soft thinking dots.
    p.eyes[0]={73,81,9*blink,5,-.32f};
    p.eyes[1]={115,77,4*blink,5,.22f};
    for (int i=0;i<3;++i) p.dots[i]=.18f+.82f*powf(.5f+.5f*sinf(t*4.2f-i*1.2f),2);
  } else if (mood==Mood::Speak) {
    p.eyes[0]={76,87+sinf(t*3)*.6f,7*blink,5,-.12f};
    p.eyes[1]={118,85+sinf(t*3)*.6f,7*blink,5,.12f};
    p.mouth=fminf(1.f,fmaxf(0.f,energy));
  } else if (mood==Mood::Sleep) {
    for (auto &e:p.eyes) {e.half=.5f;e.radius=3;e.tilt=1.3f;}
  } else if (mood==Mood::Error) {
    for (auto &e:p.eyes) {e.half=3;e.radius=6;e.tilt=0;}
  }
  return p;
}

class Motion {
  Pose pose=target(Mood::Idle,0,0);
  uint32_t lastAt=0;
public:
  const Pose &step(Mood mood,uint32_t now,float energy) {
    // Real elapsed time, capped on resume. Retarget from the displayed pose,
    // including when a new state arrives before the preceding change finishes.
    float dt=fminf((uint32_t)(now-lastAt)*.001f,.05f);
    lastAt=now;
    float a=1-expf(-dt/.09f); // ~95% of a state change within 270 ms.
    Pose next=target(mood,now,energy);
    auto blend=[a](float &v,float goal){v+=(goal-v)*a;};
    for (int i=0;i<2;++i) {
      Eye &e=pose.eyes[i]; const Eye &n=next.eyes[i];
      blend(e.x,n.x);blend(e.y,n.y);blend(e.half,n.half);
      blend(e.radius,n.radius);blend(e.tilt,n.tilt);
    }
    blend(pose.mouth,next.mouth);
    for (int i=0;i<3;++i) blend(pose.dots[i],next.dots[i]);
    return pose;
  }
};
} // namespace qiuqiu
