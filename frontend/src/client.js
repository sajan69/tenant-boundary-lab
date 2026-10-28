const messages={401:'Your session ended. Please sign in again.',403:'Access was denied. Refresh your access or sign in again.',404:'This ticket is unavailable.',409:'The change could not be saved. Reload the ticket before trying again.',413:'The request or export exceeds the allowed size.',429:'Too many sign-in attempts. Wait one minute and try again.',503:'The service is unavailable. Please try again later.'};
export class ApiError extends Error{constructor(status){super(messages[status]||'The request could not be completed. Check your input and try again.');this.status=status;}}
export function createClient(){
  let csrf='';
  return {async request(path,{method='GET',data,signal,download=false}={}){
    const response=await fetch(path,{method,credentials:'same-origin',redirect:'error',cache:'no-store',signal,
      headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRFToken':csrf},body:data===undefined?undefined:JSON.stringify(data)});
    if(!response.ok)throw new ApiError(response.status);
    if(download)return response.blob();
    const value=await response.json();
    if(value.csrf_token)csrf=value.csrf_token;
    return value;
  }};
}
