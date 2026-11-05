"""
EasyConnect v2.0 - Standalone Windows Executable (.exe) Builder
Packages the entire Python PC Agent, dependencies, and static web client into a single .exe.
"""
import os
import sys
import dis
import shutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Fix Python 3.10.0 dis module bug (bpo-45434 / IndexError on extended constants)
if sys.version_info[:3] == (3, 10, 0):
    orig_get_const_info = dis._get_const_info
    def safe_get_const_info(const_index, const_list):
        argval = const_index
        if const_list is not None and 0 <= const_index < len(const_list):
            argval = const_list[const_index]
        return argval, repr(argval)
    dis._get_const_info = safe_get_const_info

    orig_get_name_info = dis._get_name_info
    def safe_get_name_info(name_index, name_list):
        argval = name_index
        if name_list is not None and 0 <= name_index < len(name_list):
            argval = name_list[name_index]
            argrepr = argval
        else:
            argrepr = repr(argval)
        return argval, argrepr
    dis._get_name_info = safe_get_name_info

def build():
    base_dir = Path(__file__).resolve().parent
    static_dir = base_dir / "static"
    docs_dir = base_dir / "docs"
    dist_dir = base_dir / "dist"
    build_dir = base_dir / "build"
    output_exe = dist_dir / "EasyConnect.exe"
    desktop_exe = base_dir / "EasyConnect.exe"

    os.chdir(str(base_dir))

    print("=" * 65)
    print("  ⚡ EASYCONNECT - STANDALONE WINDOWS EXE BUILDER")
    print("=" * 65)
    print(f"> Project Directory: {base_dir}")
    print(f"> Static Assets:     {static_dir}")
    print(f"> Target Output:     {output_exe}")
    print("=" * 65)

    # Clean old executable files and build directories
    for old_file in [desktop_exe, output_exe]:
        if old_file.exists():
            try:
                old_file.unlink()
                print(f"> Cleaned old binary: {old_file}")
            except Exception as e:
                print(f"> Note on old file: {e}")

    icon_file = base_dir / "icon.ico"
    svg_candidates = [
        Path(r"C:\Users\choya\Downloads\download.svg"),
        base_dir / "icon.svg",
        base_dir / "download.svg",
    ]
    for svg in svg_candidates:
        if svg.exists():
            try:
                import fitz
                from PIL import Image
                import io
                doc = fitz.open(str(svg))
                page = doc[0]
                zoom = 512 / page.rect.width
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
                base_img = Image.open(io.BytesIO(pix.tobytes("png")))
                sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
                base_img.save(str(icon_file), format="ICO", sizes=sizes, bitmap_format="bmp")
                base_img.save(str(static_dir / "favicon.ico"), format="ICO", sizes=[(32, 32), (16, 16)])
                base_img.save(str(static_dir / "icon.png"), format="PNG")
                if docs_dir.exists():
                    base_img.save(str(docs_dir / "favicon.ico"), format="ICO", sizes=[(32, 32), (16, 16)])
                    base_img.save(str(docs_dir / "icon.png"), format="PNG")
                print(f"> Generated native Windows DIB icon.ico from {svg.name}")
                break
            except Exception as e:
                print(f"> Icon generation warning: {e}")

    pyi_args = [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name", "EasyConnect",
        "--add-data", f"{static_dir};static",
        "--hidden-import", "aiohttp",
        "--hidden-import", "websockets",
        "--hidden-import", "mss",
        "--hidden-import", "cv2",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "pyautogui",
        "--hidden-import", "psutil",
        "--hidden-import", "qrcode",
        "--hidden-import", "tkinter",
        "--hidden-import", "aiortc",
        "--hidden-import", "av",
        "--hidden-import", "auto_updater",
        "--hidden-import", "media_server",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(base_dir),
    ]

    if icon_file.exists():
        print(f"> Application Icon:  {icon_file}")
        pyi_args.extend(["--icon", str(icon_file)])
        pyi_args.extend(["--add-data", f"{icon_file};."])

    if docs_dir.exists():
        pyi_args.extend(["--add-data", f"{docs_dir};docs"])

    pyi_args.append(str(base_dir / "agent.py"))

    print("[1/3] Compiling and bundling Python environment via PyInstaller...")
    import PyInstaller.__main__
    try:
        PyInstaller.__main__.run(pyi_args)
    except SystemExit as e:
        if e.code != 0:
            print(f"\n❌ Build failed with exit code: {e.code}")
            return False
    except Exception as e:
        print(f"\n❌ Build error: {e}")
        return False

    if output_exe.exists():
        print("\n[2/3] Build succeeded!")
        shutil.copy2(output_exe, desktop_exe)
        size_mb = desktop_exe.stat().st_size / (1024 * 1024)
        
        # Invalidate and refresh Windows Shell icon cache
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:
            pass

        print(f"[3/3] Ready! Single-file executable created at:")
        print(f"      📍 {desktop_exe} ({size_mb:.2f} MB)")
        print("\n✅ Anyone can now download and run 'EasyConnect.exe' directly without installing Python!")
        return True
    else:
        print("\n❌ Executable not found at expected location:", output_exe)
        return False

if __name__ == "__main__":
    success = build()
    sys.exit(0 if success else 1)
