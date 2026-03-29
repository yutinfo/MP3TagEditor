# Prompt: สร้างโปรแกรม MP3 Tag Editor (Python + GUI)

## เป้าหมาย
สร้างโปรแกรม Desktop App ด้วย Python สำหรับแก้ไข metadata tag ของไฟล์ MP3
รันบน Windows ได้ และแปลงเป็น `.exe` ได้ด้วย PyInstaller

---

## Tech Stack
- **GUI**: `customtkinter` (dark/light mode, หน้าตาสวย)
- **MP3 Tag**: `mutagen` (อ่าน/เขียน ID3 tag)
- **Build**: `PyInstaller` (แปลงเป็น .exe)

ติดตั้ง dependencies:
```bash
pip install customtkinter mutagen pyinstaller
```

---

## โครงสร้าง Layout (Single Window)

```text
┌─────────────────────────────────────────────────────┐
│  🎵 MP3 Tag Editor                        [Dark ☾]  │
├─────────────────────────────────────────────────────┤
│  [📁 เลือก Folder]  path/to/folder/                 │
├──────────────────────┬──────────────────────────────┤
│  FILE LIST           │  TAG EDITOR                  │
│  ──────────────────  │  ─────────────────────────   │
│  ☑ 01 - song1.mp3   │  Title   [________________]  │
│  ☑ 02 - song2.mp3   │  Artist  [________________]  │
│  ☐ 03 - song3.mp3   │  Album   [________________]  │
│  ☑ 04 - song4.mp3   │  Year    [____]               │
│                      │  Track   [____]               │
│  [☑ Select All]      │  Genre   [________________]  │
│                      │                               │
│                      │  ┌─────────────────────────┐ │
│                      │  │ 📋 Fill Title from      │ │
│                      │  │    Filename (bulk)       │ │
│                      │  └─────────────────────────┘ │
│                      │                               │
│                      │  [💾 Save Selected Files]    │
└──────────────────────┴──────────────────────────────┘
│  Status: Ready                                       │
└─────────────────────────────────────────────────────┘
```

---

## ฟีเจอร์ที่ต้องสร้าง

### 1. เลือก Folder
- ปุ่ม "📁 เลือก Folder" เปิด folder dialog
- แสดง path ที่เลือกถัดจากปุ่ม
- โหลดไฟล์ `.mp3` ทั้งหมดใน folder นั้น (ไม่ recursive)
- แสดงรายการใน listbox พร้อม checkbox แต่ละไฟล์

### 2. File List (ซ้าย)
- แสดงชื่อไฟล์ทุกไฟล์ใน folder
- มี checkbox หน้าแต่ละไฟล์ (เลือกหลายไฟล์ได้)
- ปุ่ม "Select All / Deselect All"
- เมื่อ **คลิกเลือกไฟล์เดียว** → โหลด tag ปัจจุบันของไฟล์นั้นมาแสดงใน Tag Editor (ฝั่งขวา)

### 3. Tag Editor (ขวา)
Fields ที่แก้ไขได้:
- `Title` (TIT2)
- `Artist` (TPE1)
- `Album` (TALB)
- `Year` (TDRC)
- `Track` (TRCK)
- `Genre` (TCON)

### 4. ฟีเจอร์ "Fill Title from Filename" ⭐ (สำคัญ)
- ปุ่ม **"📋 Fill Title from Filename"**
- เมื่อกด: วนไฟล์ที่ **checked ทั้งหมด**
- นำชื่อไฟล์ (ไม่รวม `.mp3`) มาใส่เป็น `Title` tag
- ตัดเลขนำหน้าออกด้วย เช่น `01 - Song Name.mp3` → Title = `Song Name`
  - Pattern: ลบ `^\d+[\s\.\-_]+` ออกจากต้น
- แสดง preview ใน status bar ว่าจะเปลี่ยนกี่ไฟล์

### 5. Save
- ปุ่ม **"💾 Save Selected Files"**
- บันทึก tag ปัจจุบันใน form ไปยัง **ทุกไฟล์ที่ checked**
- ถ้า field ว่าง → **ไม่เขียนทับ** tag เดิม (ข้ามไป)
- แสดง status "Saved X files successfully" หรือ error message

---

## Behavior รายละเอียด

```python
# การโหลด tag เมื่อคลิกไฟล์เดียว
def on_file_select(filename):
    tags = load_mp3_tags(filename)  # ใช้ mutagen
    fill_form(tags)  # แสดงใน input fields

# Fill from filename logic
def fill_title_from_filename(files):
    import re
    for f in files:
        name = os.path.splitext(f)[0]
        # ตัด "01 - " หรือ "01. " หรือ "01_" ออก
        name = re.sub(r'^\d+[\s\.\-_]+', '', name).strip()
        set_title_tag(f, name)

# Save logic
def save_tags(files, form_data):
    for f in files:
        audio = ID3(f)
        if form_data['title']:
            audio['TIT2'] = TIT2(encoding=3, text=form_data['title'])
        if form_data['artist']:
            audio['TPE1'] = TPE1(encoding=3, text=form_data['artist'])
        # ... ต่อ field อื่นๆ
        audio.save()
```

---

## UI/UX Requirements
- Dark mode เป็น default (ใช้ `customtkinter`)
- มี toggle Dark/Light mode ที่มุมขวาบน
- Status bar ล่างสุดแสดงผลลัพธ์การทำงาน
- Font ที่อ่านง่าย รองรับภาษาไทยในชื่อไฟล์ (encoding UTF-8)
- ขนาดหน้าต่าง default: 900x600, resizable

---

## โครงสร้างไฟล์ที่ต้องสร้าง

```text
mp3-tag-editor/
├── main.py          # entry point + UI logic
├── tag_utils.py     # mutagen helper functions
├── requirements.txt
└── build.bat        # script สำหรับ PyInstaller
```

**build.bat:**
```bat
pyinstaller --onefile --windowed --name=MP3TagEditor main.py
pause
```

---

## สิ่งที่ต้องส่งมอบ
1. ไฟล์ `main.py` และ `tag_utils.py` ที่รันได้ทันที
2. ไฟล์ `requirements.txt`
3. ไฟล์ `build.bat` สำหรับ build เป็น .exe
4. คำสั่ง run และ build อย่างย่อ

---

## หมายเหตุ
- รองรับ encoding UTF-8 สำหรับชื่อไฟล์ภาษาไทย
- Handle error กรณีไฟล์ไม่มี ID3 tag (สร้างใหม่ได้เลย)
- ไม่ต้องทำ recursive subfolder ในเวอร์ชันแรก
