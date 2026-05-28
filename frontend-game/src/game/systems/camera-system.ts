// Camera follow + lerp + viewport clamp. Session D wires
// `cam.startFollow(player)` + `cam.setLerp(CAMERA_LERP)`.

import { CAMERA_LERP } from '../config/constants';

export const CameraSystem = {
  attach: (cam: import('phaser').Cameras.Scene2D.Camera, target: Phaser.GameObjects.GameObject): void => {
    cam.startFollow(target, false, CAMERA_LERP, CAMERA_LERP);
  },
};
