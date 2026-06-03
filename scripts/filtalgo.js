#!/usr/bin/env node

const path = require('path');
const { spawnSync } = require('child_process');

const cli = path.join(__dirname, '..', 'assets', 'filtalgo-cli.cjs');
const result = spawnSync(process.execPath, [cli, ...process.argv.slice(2)], {
  stdio: 'inherit',
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
