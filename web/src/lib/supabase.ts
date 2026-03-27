import { createClient } from '@supabase/supabase-js';

export const supabase = createClient(
  'https://idbvezfpkodmohebrwkc.supabase.co',
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkYnZlemZwa29kbW9oZWJyd2tjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI3NzQ2MjIsImV4cCI6MjA4ODM1MDYyMn0.l3Y4NJuo8b4L1sQrf27C82dWMkQFDwuRFF4Wk93ZJqA'
);
