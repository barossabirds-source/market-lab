import { copyFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';

mkdirSync('web/data', { recursive: true });

const config = {
  supabaseUrl: process.env.SUPABASE_URL || '',
  supabasePublishableKey: process.env.SUPABASE_PUBLISHABLE_KEY || '',
};

writeFileSync(
  'web/runtime-config.js',
  `window.MARKET_LAB_CONFIG = ${JSON.stringify(config)};\n`,
  'utf8',
);

for (const [src, dest] of [
  ['trump_events.csv', 'web/data/trump_events.csv'],
  ['trump_events_additions.csv', 'web/data/trump_events_additions.csv'],
]) {
  if (existsSync(src)) copyFileSync(src, dest);
}

console.log(`Market Lab config built. Supabase configured: ${Boolean(config.supabaseUrl && config.supabasePublishableKey)}`);
