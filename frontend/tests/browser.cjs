const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const payload='<img src=x onerror=alert(1)>';
function fixture(...args){execFileSync(process.env.PYTHON_EXECUTABLE||'python',[path.join(__dirname,'lab_state.py'),...args],{cwd:root,stdio:'pipe'});}
(async()=>{
 const password=process.env.BOUNDARY_DEMO_PASSWORD;if(!password)throw new Error('Synthetic demo password required');
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']}: {})});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();
 const failures=[];const checks=[];let created;
 page.on('pageerror',error=>failures.push(error.message));page.on('dialog',()=>failures.push('Unexpected script dialog'));
 async function check(name,run){let timer;try{await Promise.race([run(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Timed out: '+name)),45000)})]);checks.push({name,result:'passed'});console.log('Passed:',name);}finally{clearTimeout(timer);}}
 async function signIn(name){await page.getByLabel('Username',{exact:true}).fill(name);await page.getByLabel('Password',{exact:true}).fill(password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.locator('#organization').waitFor();await page.locator('.ticket-row').first().waitFor();}
 async function download(){const pending=page.waitForEvent('download');await page.getByRole('button',{name:'Export JSON',exact:true}).click();return JSON.parse(await fs.readFile(await (await pending).path(),'utf8'));}
 try{
  for(let attempt=0;;attempt++){try{await page.goto('http://127.0.0.1:4173/');break;}catch(error){if(attempt>=30)throw error;await page.waitForTimeout(150);}}
  await page.getByRole('heading',{name:'Welcome back'}).waitFor();
  await check('session login and tenant-specific viewer controls',async()=>{
   await signIn('sam');assert.equal(await page.locator('#organization').inputValue(),A);assert.equal(await page.getByRole('button',{name:'New ticket',exact:true}).count(),0);
   await page.locator('.ticket-row').filter({hasText:'Synthetic Cedar request'}).click();await page.locator('.detail h2').waitFor();assert.equal(await page.getByRole('button',{name:'Save changes',exact:true}).count(),0);
  });
  await check('viewer forged write is denied by the API',async()=>{
   const status=await page.evaluate(async A=>{const session=await(await fetch('/api/session/')).json();return(await fetch(`/api/tenants/${A}/tickets/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':session.csrf_token},body:JSON.stringify({title:'Denied viewer attempt'})})).status;},A);assert.equal(status,403);
  });
  await check('viewer JSON download is scoped',async()=>{const report=await download();assert.equal(report.tenant_id,A);assert.ok(report.tickets.every(ticket=>ticket.tenant_id===A));assert.equal(report.tickets.length,1);});
  await check('late previous-tenant response cannot replace new tenant data',async()=>{
   let held,release,finished;const heldPromise=new Promise(resolve=>held=resolve),releasePromise=new Promise(resolve=>release=resolve),finishedPromise=new Promise(resolve=>finished=resolve);
   const pattern=`**/api/tenants/${A}/tickets/?*`;
   await page.route(pattern,async route=>{try{const response=await route.fetch();held();await releasePromise;await route.fulfill({response});}catch(error){/* A canceled old request is an expected safe outcome. */}finally{finished();}});
   await page.getByRole('button',{name:'Reload tickets',exact:true}).click();await heldPromise;
   await page.locator('#organization').selectOption(B);await page.locator('.ticket-row').filter({hasText:'Synthetic Harbor request'}).waitFor();release();await finishedPromise;await page.unroute(pattern);
   assert.equal(await page.locator('#organization').inputValue(),B);assert.equal(await page.locator('.ticket-row').filter({hasText:'Synthetic Cedar request'}).count(),0);
  });
  await check('editor creates edits and comments with inert HTML text',async()=>{
   await page.getByRole('button',{name:'New ticket',exact:true}).click();await page.getByLabel('New ticket title',{exact:true}).fill(payload);
   const pending=page.waitForResponse(response=>response.url().endsWith(`/api/tenants/${B}/tickets/`)&&response.request().method()==='POST');
   await page.getByRole('button',{name:'Create ticket',exact:true}).click();const response=await pending;assert.equal(response.status(),201);created=(await response.json()).ticket.id;
   await page.getByRole('heading',{name:payload,exact:true}).waitFor();assert.equal(await page.locator('img').count(),0);
   await page.getByRole('combobox',{name:'Ticket status',exact:true}).selectOption('closed');await page.getByRole('button',{name:'Save changes',exact:true}).click();await page.locator('.detail .notice').filter({hasText:'Changes saved.'}).waitFor();assert.equal(await page.locator('.detail-heading .badge').textContent(),'closed');
   await page.getByLabel('Add a comment',{exact:true}).fill('Hello\n<script>alert(1)</script>');await page.getByRole('button',{name:'Post comment',exact:true}).click();await page.locator('.comments p').filter({hasText:'<script>alert(1)</script>'}).waitFor();assert.equal(await page.locator('img').count(),0);
  });
  await check('status filters and editor export preserve scope',async()=>{
   await page.getByRole('combobox',{name:'Status filter',exact:true}).selectOption('closed');await page.locator('.ticket-row').filter({hasText:payload}).waitFor();
   await page.getByRole('combobox',{name:'Status filter',exact:true}).selectOption('open');await page.locator('.ticket-row').filter({hasText:'Synthetic Harbor request'}).waitFor();assert.equal(await page.locator('.ticket-row').filter({hasText:payload}).count(),0);
   const report=await download();assert.equal(report.tenant_id,B);assert.ok(report.tickets.every(ticket=>ticket.tenant_id===B));assert.ok(report.tickets.some(ticket=>ticket.id===created));
  });
  await check('revocation clears visible records and refreshes membership',async()=>{
   fixture('revoke');try{await page.getByRole('button',{name:'Reload tickets',exact:true}).click();await page.getByRole('heading',{name:'Access needs refreshing'}).waitFor();assert.equal(await page.locator('.ticket-row').count(),0);assert.equal(await page.locator('.detail').count(),0);
    await page.getByRole('button',{name:'Refresh access',exact:true}).click();await page.locator('.ticket-row').filter({hasText:'Synthetic Cedar request'}).waitFor();assert.equal(await page.locator('#organization option').count(),1);assert.equal(await page.getByRole('button',{name:'New ticket',exact:true}).count(),0);
   }finally{fixture('restore');}
  });
  await check('logout clears records and a different user gets fresh permissions',async()=>{
   await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByRole('heading',{name:'Welcome back'}).waitFor();assert.equal(await page.locator('.ticket-row').count(),0);assert.equal(await page.getByLabel('Password',{exact:true}).inputValue(),'');
   await signIn('bob');assert.equal(await page.locator('#organization option').count(),1);assert.equal(await page.locator('#organization').inputValue(),B);assert.equal(await page.getByRole('button',{name:'New ticket',exact:true}).count(),0);
  });
  await check('expired session returns to sign-in without retained ticket state',async()=>{
   await context.clearCookies({name:'sessionid'});await page.getByRole('button',{name:'Reload tickets',exact:true}).click();await page.getByRole('heading',{name:'Welcome back'}).waitFor();assert.equal(await page.locator('.ticket-row').count(),0);
  });
  await check('responsive layout security headers and no browser storage',async()=>{
   await signIn('alice');await page.locator('.ticket-row').filter({hasText:'Synthetic Cedar request'}).click();await page.locator('.detail h2').waitFor();
   await fs.mkdir(path.join(root,'artifacts'),{recursive:true});await page.screenshot({path:path.join(root,'artifacts/tenant-desktop.png'),fullPage:true});
   await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.screenshot({path:path.join(root,'artifacts/tenant-mobile.png'),fullPage:true});
   assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length})),{local:0,session:0});const response=await context.request.get('http://127.0.0.1:4173/');assert.match(response.headers()['content-security-policy'],/frame-ancestors 'none'/);
  });
  assert.deepEqual(failures,[]);await fs.writeFile(path.join(root,'artifacts/browser-checks.json'),JSON.stringify({source:'synthetic_seed',backend:'real Django and PostgreSQL',client:'built React through loopback Vite preview',checks,limitations:'Functional lab cases, not an exhaustive security assessment.'},null,2));
 }catch(error){await fs.mkdir(path.join(root,'artifacts'),{recursive:true});await page.screenshot({path:path.join(root,'artifacts/tenant-failure.png'),fullPage:true}).catch(()=>{});await fs.writeFile(path.join(root,'artifacts/browser-partial.json'),JSON.stringify({failed:true,checks},null,2));throw error;}finally{try{fixture('restore');if(created)fixture('cleanup',created);fixture('check');}finally{await browser.close();}}
})().catch(error=>{console.error(error);process.exitCode=1});
