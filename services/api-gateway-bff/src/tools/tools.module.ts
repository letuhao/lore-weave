// FE→MCP-tool bridge module — wires the locally-served ToolsController
// (POST /v1/ai/tools/execute). No providers: the controller validates the JWT and
// forwards to ai-gateway over fetch (the grounding/notifications precedent).

import { Module } from '@nestjs/common';
import { ToolsController } from './tools.controller';

@Module({
  controllers: [ToolsController],
})
export class ToolsModule {}
