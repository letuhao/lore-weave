/** Jest runs in ESM mode: NestJS 12 (@nestjs/*) ships ESM-only, so ts-jest
 *  must emit ESM (useESM) and jest must load it with the ESM runtime
 *  (NODE_OPTIONS=--experimental-vm-modules, set in the test script). The
 *  moduleNameMapper strips the `.js` suffix the node16 source uses on relative
 *  imports so `./foo.js` resolves to `foo.ts`. */
module.exports = {
  testEnvironment: 'node',
  rootDir: '.',
  testMatch: ['**/test/**/*.spec.ts'],
  moduleFileExtensions: ['ts', 'js', 'json'],
  moduleNameMapper: {
    '^(\\.{1,2}/.*)\\.js$': '$1',
  },
  transform: {
    '^.+\\.ts$': ['ts-jest', { tsconfig: 'tsconfig.spec.json', useESM: true }],
  },
  extensionsToTreatAsEsm: ['.ts'],
};
