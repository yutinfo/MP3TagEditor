# MP3 Tag Editor

Desktop app สำหรับจัดการ MP3 metadata บน Windows ด้วย Python + GUI โดยใช้ `customtkinter` สำหรับหน้าตาแอป และ `mutagen` สำหรับอ่าน/เขียน ID3 tags

## Features
- โหลดไฟล์ MP3 แบบ recursive จากโฟลเดอร์และ subfolder ทั้งหมด
- แสดงรายการไฟล์แบบ tree พร้อม folder checkbox และยุบ/ขยายโฟลเดอร์ได้
- แก้ไข tag หลัก:
  - `Title`
  - `Artist`
  - `Album`
  - `Year`
  - `Track`
  - `Genre`
- `Fill Title from Filename` สำหรับดึงชื่อไฟล์มาใส่ title
- รองรับ cover art (`APIC`)
  - preview รูปปกปัจจุบัน
  - เลือก `JPG/PNG`
  - apply/remove กับหลายไฟล์
- รองรับ rename ชื่อไฟล์ MP3
- dark/light mode
- confirm popup แบบธีมเดียวกับแอป

## Important Save Behavior
- การแก้ไขแต่ละไฟล์ถูกเก็บเป็น draft แยกกันในแอป
- ตอนกด `Save Selected Files` ระบบจะบันทึกข้อมูลของแต่ละไฟล์ตาม draft ของไฟล์นั้น
- จะไม่เอาค่าที่โชว์อยู่บนหน้าจอไปทับทุกไฟล์แบบ broadcast

## Requirements
- Python 3.10+ แนะนำบน Windows

ติดตั้ง dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Build EXE

ใช้ไฟล์ batch:

```bat
build.bat
```

หรือรันตรง:

```bash
pyinstaller --onefile --windowed --name=MP3TagEditor main.py
```

## Project Structure

```text
MP3TagEditor/
├── main.py
├── tag_utils.py
├── requirements.txt
├── build.bat
├── README.md
└── AI-HANDOFF.md
```

## Main Files
- `main.py`
  - UI
  - folder tree
  - per-file drafts
  - rename / cover / save flow
- `tag_utils.py`
  - recursive MP3 scanning
  - ID3 read/write helpers
  - cover art helpers
  - rename helper
- `AI-HANDOFF.md`
  - บันทึกสถานะงานปัจจุบันสำหรับ AI หรือคนที่มารับช่วงต่อ

## Notes
- รองรับชื่อไฟล์และ tag ภาษาไทย
- cover art ใช้ ID3 frame ชนิด `APIC`
- ถ้าไฟล์ยังไม่มี ID3 tag ระบบสามารถสร้างให้ได้

## Handoff
ถ้าจะให้ AI ตัวอื่นทำงานต่อ แนะนำให้อ่าน `AI-HANDOFF.md` ควบคู่กับไฟล์นี้ก่อน เพื่อเข้าใจ logic สำคัญ โดยเฉพาะเรื่อง per-file drafts และ workflow การ save
