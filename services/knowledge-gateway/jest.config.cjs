/** knowledge-gateway jest config (.cjs — package.json is "type": "module" for the ESM
 *  runtime, so the jest config must be CommonJS explicitly). Tests run under CommonJS
 *  (tsconfig.spec.json); moduleNameMapper strips the `.js` suffix the node16 source uses on
 *  relative imports so `./foo.js` resolves to `foo.ts`. */
module.exports = {
  testEnvironment: 'node',
  rootDir: '.',
  testMatch: ['**/test/**/*.spec.ts'],
  moduleFileExtensions: ['ts', 'js', 'json'],
  moduleNameMapper: {
    '^(\\.{1,2}/.*)\\.js$': '$1',
  },
  transform: {
    '^.+\\.ts$': ['ts-jest', { tsconfig: 'tsconfig.spec.json' }],
  },
};
