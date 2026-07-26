// M2 — wires the locally-served HomeController (GET /v1/home, GET /v1/activity,
// POST /v1/activity/mark-all-read). No providers: the controller validates the JWT and fans out
// to the public service APIs over fetch (the AssistantController precedent).
import { Module } from '@nestjs/common';
import { HomeController } from './home.controller';

@Module({
  controllers: [HomeController],
})
export class HomeModule {}
