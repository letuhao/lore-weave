// WS-1.4 — wires the locally-served AssistantController (POST /v1/assistant/provision).
// No providers: the controller validates the JWT and fans out to the public service APIs
// over fetch (the ToolsController precedent).

import { Module } from '@nestjs/common';
import { AssistantController } from './assistant.controller';

@Module({
  controllers: [AssistantController],
})
export class AssistantModule {}
