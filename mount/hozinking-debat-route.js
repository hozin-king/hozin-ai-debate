// Potongan mount SIAP PAKAI untuk hozinking.my.id — TIDAK diterapkan otomatis.
// Cara pakai (oleh pemilik worker hozinwate-web, di luar repo ini):
// tambahkan di handler fetch worker, SEBELUM fallback homepage:
//
//   if (url.pathname === '/debat' || url.pathname.startsWith('/debat/')) {
//     const target = 'https://hozin-king.github.io/hozin-ai-debate/'
//       + url.pathname.replace(/^\/debat\/?/, '');
//     const res = await fetch(target + url.search);
//     const html = await res.text();
//     // Halaman memakai path relatif data/, jadi arahkan ke Pages absolut:
//     const fixed = html.replaceAll('"data/', '"https://hozin-king.github.io/hozin-ai-debate/data/');
//     return new Response(fixed, { headers: { 'content-type': 'text/html;charset=UTF-8' } });
//   }
//
// Catatan: potongan ini hanya proxy halaman statis + JSON dari GitHub Pages.
// Tidak ada secret, tidak ada penulisan data, tidak menambah beban D1.
export {};
