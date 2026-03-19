#!/usr/bin/env node
const prompt = process.argv.slice(2).join(' ') || 'build me a simple dashboard';
const fs = require('fs');

function log(msg) {
  const line = '[' + new Date().toLocaleTimeString() + '] ' + msg;
  console.log(line);
  fs.appendFileSync('/tmp/v0-deploy.log', line + '\n');
}

async function main() {
  const { v0 } = await import('v0-sdk');
  log('🚀 Starting v0 build: ' + prompt);
  const start = Date.now();
  const chat = await v0.chats.create({ message: prompt });
  const elapsed = ((Date.now()-start)/1000).toFixed(1);
  log('✅ Built in ' + elapsed + 's');
  log('DEMO_URL: ' + chat.demo);
  log('CHAT_ID: ' + chat.id);
  console.log('DEMO_URL:', chat.demo);
  console.log('CHAT_ID:', chat.id);
}

main().catch(e => { 
  const msg = 'ERROR: ' + e.message;
  fs.appendFileSync('/tmp/v0-deploy.log', msg + '\n');
  console.error(msg); 
  process.exit(1); 
});
