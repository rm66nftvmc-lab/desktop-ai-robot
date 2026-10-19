// Display-state protocol shared with bridge/app/faces.py. No bitmap artwork.
#pragma once
#include <stdint.h>
#define FACE_COUNT 8
enum {
  FACE_ID_BOOT = 0,
  FACE_ID_READY = 1,
  FACE_ID_SLEEP = 2,
  FACE_ID_LISTEN = 3,
  FACE_ID_THINK = 4,
  FACE_ID_SPEAK = 5,
  FACE_ID_APPROVE = 6,
  FACE_ID_ERROR = 7,
};
