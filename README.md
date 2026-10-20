![SeretAje](docs/seretaje-preview.png)

# SeretAje

Tahan **Shift** sambil menyeret file dari File Explorer atau Desktop. Cincin pilihan muncul di samping kursor, lepas file di pilihan yang diinginkan. File asal tidak pernah diubah atau dipindah, hasilnya disimpan di folder yang sama dengan nama baru (misalnya `foto - dipotong.jpg`).

## Pilihan di cincin

| Bagian | Fungsi | Gambar | PDF |
|---|---|---|---|
| Tengah | Ubah format | JPG, PNG, WEBP, PDF, ICO | JPG, PNG (tiap halaman) |
| Kecilkan | Perkecil ukuran file | ya | ya |
| Metadata | Hapus EXIF, lokasi GPS, info pembuat | ya | ya |
| Edit | Putar, cermin, kecerahan, kontras, saturasi, ketajaman, ukuran | ya | halaman dipilih jadi PNG |
| Tandai | Pena, stabilo, panah, kotak, teks | ya | halaman dipilih jadi PNG |
| Latar | Pasang di atas latar gradasi atau warna, sudut membulat, bayangan | ya | halaman dipilih jadi PNG |
| Potong | Potong dengan rasio bebas, 1:1, 4:3, 3:4, 16:9, A4 | ya | semua halaman |
| Sensor | Blok hitam, buram, atau piksel | ya | blok hitam, teks di bawahnya dihapus permanen |

## Gabung gambar jadi PDF

Lepas satu atau beberapa gambar di **PDF** (tengah cincin), atau klik kanan ikon di area jam lalu pilih **Gabung gambar jadi PDF**. Jendela pengaturan terbuka:

- Ukuran kertas A4, F4/Folio, Letter, Legal, A5, atau mengikuti ukuran gambar.
- Arah kertas otomatis, tegak, atau mendatar. Gambar per halaman 1, 2, atau 4.
- Tepi kertas tanpa, 5, 10, atau 20 mm. Gambar tampil utuh atau memenuhi halaman.
- Kualitas tinggi, sedang, atau kecil.
- Urutan diatur dengan menyeret gambar, tombol geser, urutkan nama, atau balik urutan. Gambar bisa diputar dan dihapus.
- Tambah gambar dengan menyeret dari Explorer, tombol Tambah gambar, atau Ctrl+V dari papan klip.
- Nama file otomatis dari nama gambar pertama sampai tanda `_`, bisa diketik ulang. PDF disimpan di folder gambar pertama.
- Pengaturan terakhir diingat.

Gambar dan PDF campuran yang dilepas di PDF tetap langsung digabung jadi satu PDF tanpa jendela pengaturan.

## Cara menjalankan

1. Pasang Python 3.10 atau lebih baru dari python.org, centang "Add python.exe to PATH".
2. Klik dua kali `jalankan.bat`. Pertama kali akan memasang kebutuhan (beberapa menit).
3. Ikon SeretAje muncul di area jam. Klik kanan ikonnya untuk pengaturan:
   - **Aktif**: matikan sementara.
   - **Hanya dari File Explorer dan Desktop**: supaya cincin tidak muncul saat Shift+seret di aplikasi lain.
   - **Jalankan saat Windows menyala**.
   - **Tampilkan cincin sekarang**: cincin tetap terbuka, tinggal seret file ke sana. Klik kiri ikon juga sama.

## Shortcut

Saat pertama kali menjalankan `jalankan.bat`, shortcut dibuat otomatis. Bisa juga dibuat ulang lewat `buat-shortcut.bat` atau menu ikon di area jam.

| Shortcut | Lokasi | Tombol pintas |
|---|---|---|
| SeretAje | Desktop dan Start Menu | Ctrl+Alt+S, membuka cincin di posisi kursor |
| Gabung Gambar jadi PDF | Desktop dan Start Menu | Ctrl+Alt+G, membuka jendela Gabung PDF |

Kalau SeretAje sudah berjalan, membuka shortcut tidak menjalankan salinan kedua, tetapi langsung memunculkan cincin atau jendela Gabung PDF.

## Jadi satu file .exe

Klik dua kali `buat-exe.bat`. Hasilnya `dist\SeretAje.exe`, bisa dipindah ke komputer lain tanpa Python. Setelah itu jalankan `buat-shortcut.bat` lagi supaya shortcut mengarah ke file .exe.

## Catatan

- Saat menyeret dengan Shift, Explorer menampilkan tulisan "Move to". SeretAje selalu meminta salinan, jadi file asal tetap di tempatnya.
- Ikon di area jam masih sementara (huruf S).
- File HEIC dari iPhone bisa dibuka kalau `pillow-heif` berhasil terpasang.
