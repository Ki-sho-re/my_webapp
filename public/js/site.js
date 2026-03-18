// site.js - small helper
document.addEventListener('DOMContentLoaded', function(){
  const btn = document.querySelector('.menu-toggle');
  if(btn){
    btn.addEventListener('click', () => document.querySelector('.main-nav').classList.toggle('open'));
  }
});
