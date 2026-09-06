import { Module } from '@nestjs/common';
import { HealthController } from './health/health.controller.js';
import { KalReadController } from './kal/kal-read.controller.js';
import { KalProjectReadController } from './kal/kal-project-read.controller.js';
import { KalWriteController } from './kal/kal-write.controller.js';

@Module({
  controllers: [HealthController, KalReadController, KalProjectReadController, KalWriteController],
})
export class AppModule {}
