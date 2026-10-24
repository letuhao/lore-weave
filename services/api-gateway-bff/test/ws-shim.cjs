/**
 * Jest-ESM interop shim for the `ws` package (mapped via moduleNameMapper).
 * jest's ESM loader cannot take the named exports (`Server`, …) out of `ws`'s
 * CJS surface — its namespace comes back empty — while node's own interop
 * handles it. This CJS shim re-exports the names through the exact
 * `module.exports.Name = …` assignment shape cjs-module-lexer CAN see, so the
 * ESM `import { Server } from 'ws'` keeps working in tests; the production
 * build keeps the real `ws`.
 *
 * The require below goes by a RELATIVE path into node_modules on purpose: the
 * moduleNameMapper matches the bare specifier `ws`, and a literal `require('ws')`
 * inside this shim would map onto the shim itself (a circular self-require that
 * left every re-exported name undefined).
 */
const ws = require('../node_modules/ws');

module.exports.Server = ws.Server;
module.exports.WebSocket = ws.WebSocket;
module.exports.WebSocketServer = ws.WebSocketServer;
module.exports.default = ws;
