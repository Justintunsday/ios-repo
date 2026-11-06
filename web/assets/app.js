const copy=document.querySelector('#copy-source');
copy?.addEventListener('click',async()=>{
  const value=document.querySelector('#source-url').textContent;
  const status=document.querySelector('#copy-status');
  try{await navigator.clipboard.writeText(value);copy.textContent='Copied';status.textContent='Source URL copied.';}
  catch{const range=document.createRange();range.selectNodeContents(document.querySelector('#source-url'));getSelection().removeAllRanges();getSelection().addRange(range);status.textContent='URL selected. Copy it with your browser.';}
});
