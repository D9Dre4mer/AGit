# AGit - Auto Commit GUI Application

Ứng dụng desktop đơn giản với giao diện đẹp mắt để tự động commit Git với commit message được tạo bởi Gemini AI.

## Tính năng

- 🎨 Giao diện đẹp mắt với màu xanh rừng thẳm giống GitHub Desktop
- 🤖 Tự động tạo commit message thông minh bằng Gemini AI
- 📦 Tự động add, commit và push (tùy chọn)
- 🚀 Chạy như file exe, không cần cài Python
- ⚡ Đơn giản, dễ sử dụng

## Yêu cầu

- Windows 10/11
- Git đã được cài đặt trên máy
- Gemini API Key (lấy tại [Google AI Studio](https://makersuite.google.com/app/apikey))

## Cài đặt và Sử dụng

### Cách 1: Sử dụng file exe (Khuyến nghị)

1. Tải file `AGit.exe` từ releases
2. Tạo file `.env` trong cùng thư mục với `AGit.exe`
3. Mở file `.env` và thêm dòng sau:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
   Thay `your_api_key_here` bằng API key thực tế của bạn
4. Chạy `AGit.exe`

### Cách 2: Chạy từ source code

1. Clone repository:
   ```bash
   git clone <repository-url>
   cd AGit
   ```

2. Create and activate virtual environment:
   
   **Windows (PowerShell):**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
   
   **Windows (CMD):**
   ```cmd
   python -m venv venv
   venv\Scripts\activate.bat
   ```
   
   **Linux/Mac:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Create `.env` file:
   ```bash
   copy .env.example .env
   ```
   Then open `.env` file and fill in your `GEMINI_API_KEY`

5. Run the application:
   ```bash
   python main.py
   ```

## Build Executable

Để build file exe từ source code:

1. Cài đặt PyInstaller:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Build exe:
   ```bash
   python build_exe.py
   ```
   
   Hoặc sử dụng spec file:
   ```bash
   pyinstaller AGit.spec
   ```

3. File exe sẽ được tạo tại `dist/AGit.exe`

## Hướng dẫn sử dụng

1. **Nhập đường dẫn repository**: 
   - Nhập đường dẫn đến thư mục Git repository của bạn
   - Hoặc click nút "Browse" để chọn thư mục

2. **Chọn có push hay không**:
   - Tick vào checkbox "Push to remote after commit" nếu muốn tự động push sau khi commit
   - Bỏ tick nếu chỉ muốn commit local

3. **Click "Auto Commit"**:
   - Chương trình sẽ tự động:
     - Kiểm tra thay đổi
     - Tạo commit message bằng AI
     - Add và commit
     - Push (nếu đã tick checkbox)

4. **Xem kết quả**:
   - Status sẽ hiển thị ở phía dưới
   - Màu xanh = thành công
   - Màu đỏ = có lỗi

## Cấu trúc dự án

```
AGit/
├── main.py              # File chính chứa GUI và logic
├── git_handler.py       # Module xử lý Git commands
├── gemini_client.py     # Module tích hợp Gemini API
├── .env                 # File chứa Gemini API key (tự tạo)
├── .env.example         # Template cho .env
├── requirements.txt     # Dependencies
├── requirements-dev.txt # Dev dependencies (PyInstaller)
├── build_exe.py         # Script để build executable
├── AGit.spec            # PyInstaller spec file
└── README.md            # File này
```

## Troubleshooting

### Lỗi "GEMINI_API_KEY không được tìm thấy"
- Đảm bảo file `.env` nằm cùng thư mục với `AGit.exe`
- Kiểm tra file `.env` có đúng format: `GEMINI_API_KEY=your_key`

### Lỗi "Đường dẫn không phải là Git repository"
- Đảm bảo đường dẫn trỏ đến thư mục có chứa `.git`
- Thử chọn lại thư mục bằng nút "Browse"

### Lỗi khi push
- Kiểm tra repository đã có remote chưa: `git remote -v`
- Kiểm tra đã đăng nhập Git chưa
- Kiểm tra quyền truy cập remote repository

### Lỗi API Gemini
- Kiểm tra API key có đúng không
- Kiểm tra kết nối internet
- Kiểm tra quota API còn không

## License

MIT License - Xem file [LICENSE](LICENSE) để biết thêm chi tiết.

## Tác giả

D9Dre4mer
