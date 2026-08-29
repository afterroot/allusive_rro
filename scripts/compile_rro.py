#!/usr/bin/env python3
import os
import sys
import shutil
import tempfile
import argparse
import subprocess
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw

DENSITIES = {
    "drawable-mdpi-v4": (24, 24),
    "drawable-hdpi-v4": (36, 36),
    "drawable-xhdpi-v4": (48, 48),
    "drawable-xxhdpi-v4": (72, 72),
    "drawable-xxxhdpi-v4": (96, 96),
    "drawable-nodpi-v4": (96, 96),
    "drawable": (96, 96),
}


def find_android_tools():
    sdk_root = (
        os.environ.get("ANDROID_HOME")
        or os.environ.get("ANDROID_SDK_ROOT")
        or os.path.expanduser("~/Android/Sdk")
    )
    aapt2 = shutil.which("aapt2")
    zipalign = shutil.which("zipalign")
    apksigner = shutil.which("apksigner")
    android_jar = None

    if os.path.isdir(sdk_root):
        bt_dir = Path(sdk_root) / "build-tools"
        if bt_dir.is_dir():
            versions = sorted(bt_dir.iterdir(), key=lambda p: p.name)
            if versions:
                latest_bt = versions[-1]
                if not aapt2 and (latest_bt / "aapt2").is_file():
                    aapt2 = str(latest_bt / "aapt2")
                if not zipalign and (latest_bt / "zipalign").is_file():
                    zipalign = str(latest_bt / "zipalign")
                if not apksigner and (latest_bt / "apksigner").is_file():
                    apksigner = str(latest_bt / "apksigner")
        platforms_dir = Path(sdk_root) / "platforms"
        if platforms_dir.is_dir():
            platforms = sorted(
                platforms_dir.glob("android-*/android.jar"), key=lambda p: p.parent.name
            )
            if platforms:
                android_jar = str(platforms[-1])

    if not aapt2 or not zipalign or not apksigner or not android_jar:
        print(
            "[!] Error: Could not locate Android SDK build tools (aapt2, zipalign, apksigner, android.jar)"
        )
        print("    Please ensure ANDROID_HOME or ANDROID_SDK_ROOT is set properly.")
        sys.exit(1)
    return aapt2, zipalign, apksigner, android_jar


def create_preset_image(style="glow_cyan", color_hex=None, size=96):
    scale = 4
    img_size = size * scale
    center = img_size // 2
    img = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))

    color = hex_to_rgb(color_hex) if color_hex else (0, 229, 255)
    if style == "glow_purple":
        color = hex_to_rgb(color_hex) if color_hex else (180, 50, 255)
    elif style == "glow_red":
        color = hex_to_rgb(color_hex) if color_hex else (255, 45, 85)
    elif style == "glow_amber":
        color = hex_to_rgb(color_hex) if color_hex else (255, 170, 0)

    if "glow" in style:
        core_r = int(img_size * 0.20)
        glow_r = int(img_size * 0.46)
        step = max(2, 4 * scale)
        for r in range(glow_r, core_r, -step):
            ratio = 1.0 - ((r - core_r) / (glow_r - core_r))
            draw.ellipse(
                [center - r, center - r, center + r, center + r],
                fill=(color[0], color[1], color[2], int(ratio * 160)),
            )
        draw.ellipse(
            [
                center - int(core_r * 1.5),
                center - int(core_r * 1.5),
                center + int(core_r * 1.5),
                center + int(core_r * 1.5),
            ],
            outline=(color[0], color[1], color[2], 255),
            width=2 * scale,
        )
        draw.ellipse(
            [center - core_r, center - core_r, center + core_r, center + core_r],
            fill=(255, 255, 255, 255),
        )
    elif style == "crosshair":
        r = int(img_size * 0.35)
        w = max(1, 2 * scale)
        draw.ellipse(
            [center - r, center - r, center + r, center + r],
            outline=(color[0], color[1], color[2], 240),
            width=w,
        )
        tick_len = int(r * 0.4)
        draw.line(
            [(center, center - r - tick_len), (center, center - r + tick_len)],
            fill=(color[0], color[1], color[2], 255),
            width=w,
        )
        draw.line(
            [(center, center + r - tick_len), (center, center + r + tick_len)],
            fill=(color[0], color[1], color[2], 255),
            width=w,
        )
        draw.line(
            [(center - r - tick_len, center), (center - r + tick_len, center)],
            fill=(color[0], color[1], color[2], 255),
            width=w,
        )
        draw.line(
            [(center + r - tick_len, center), (center + r + tick_len, center)],
            fill=(color[0], color[1], color[2], 255),
            width=w,
        )
        draw.ellipse(
            [center - 4, center - 4, center + 4, center + 4], fill=(255, 255, 255, 255)
        )
    else:
        r = int(img_size * 0.35)
        draw.ellipse(
            [center - r, center - r + 4, center + r, center + r + 4], fill=(0, 0, 0, 90)
        )
        draw.ellipse(
            [center - r, center - r + center, center + r, center + r],
            fill=(255, 255, 255, 230),
            outline=(0, 0, 0, 120),
            width=2 * scale,
        )
    return img.resize((size, size), Image.Resampling.LANCZOS)


def build_rro(
    image_path=None,
    style="glow_cyan",
    color=None,
    package_name="com.afterroot.allusive_rro",
    target_package="android",
    output_apk="build/allusive_rro.apk",
    priority=99,
    keystore_path=None,
    keystore_pass="android",
    key_alias="androiddebugkey",
    key_pass="android",
):
    aapt2, zipalign, apksigner, android_jar = find_android_tools()
    print(f"[*] Building RRO APK: {output_apk}")
    print(f"    - Overlay Package: {package_name}")
    print(f"    - Target Package:  {target_package}")

    if image_path and os.path.isfile(image_path):
        print(f"    - Input Image:     {image_path}")
        base_img = Image.open(image_path).convert("RGBA")
    else:
        print(f"    - Preset Style:    {style}")
        base_img = create_preset_image(style=style, color_hex=color)

    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        res_dir = src_dir / "res"
        res_dir.mkdir(parents=True)

        manifest_path = src_dir / "AndroidManifest.xml"
        manifest_path.write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{package_name}"
    android:versionCode="2"
    android:versionName="2.0">
    <uses-sdk android:minSdkVersion="28" android:targetSdkVersion="34" />
    <overlay android:targetPackage="{target_package}" android:resourcesMap="@xml/overlays" android:priority="{priority}" android:isStatic="true" />
    <application android:hasCode="false" android:label="Pointer Overlay" />
</manifest>
""")

        xml_dir = res_dir / "xml"
        xml_dir.mkdir(parents=True, exist_ok=True)
        (xml_dir / "overlays.xml").write_text("""<?xml version="1.0" encoding="utf-8"?>
<overlay xmlns:android="http://schemas.android.com/apk/res/android">
    <item target="drawable/pointer_spot_touch" value="@drawable/pointer_spot_touch" />
    <item target="drawable/pointer_spot_hover" value="@drawable/pointer_spot_hover" />
    <item target="drawable/pointer_spot_anchor" value="@drawable/pointer_spot_anchor" />
    <item target="drawable/pointer_spot_touch_icon" value="@drawable/pointer_spot_touch_icon" />
    <item target="drawable/pointer_spot_hover_icon" value="@drawable/pointer_spot_hover_icon" />
    <item target="drawable/pointer_spot_anchor_icon" value="@drawable/pointer_spot_anchor_icon" />
</overlay>
""")

        drawable_dir = res_dir / "drawable"
        drawable_dir.mkdir(parents=True, exist_ok=True)
        xml_descriptors = {
            "pointer_spot_touch_icon.xml": "@drawable/pointer_spot_touch",
            "pointer_spot_hover_icon.xml": "@drawable/pointer_spot_hover",
            "pointer_spot_anchor_icon.xml": "@drawable/pointer_spot_anchor",
        }
        for xml_name, bitmap_ref in xml_descriptors.items():
            (drawable_dir / xml_name).write_text(
                f"""<?xml version="1.0" encoding="utf-8"?>
<pointer-icon xmlns:android="http://schemas.android.com/apk/res/android"
    android:bitmap="{bitmap_ref}"
    android:hotSpotX="12dp"
    android:hotSpotY="12dp" />
"""
            )

        for folder_name, size in DENSITIES.items():
            folder_path = res_dir / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            resized = base_img.resize(size, Image.Resampling.LANCZOS)
            resized.save(folder_path / "pointer_spot_touch.png", "PNG")
            resized.save(folder_path / "pointer_spot_hover.png", "PNG")
            resized.save(folder_path / "pointer_spot_anchor.png", "PNG")

        compiled_zip = Path(tmpdir) / "compiled.zip"
        subprocess.run(
            [aapt2, "compile", "--dir", str(res_dir), "-o", str(compiled_zip)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        unaligned_apk = Path(tmpdir) / "unaligned.apk"
        subprocess.run(
            [
                aapt2,
                "link",
                "-I",
                android_jar,
                "--manifest",
                str(manifest_path),
                "-o",
                str(unaligned_apk),
                str(compiled_zip),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        aligned_apk = Path(tmpdir) / "aligned.apk"
        subprocess.run(
            [zipalign, "-p", "-f", "4", str(unaligned_apk), str(aligned_apk)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        if keystore_path and os.path.isfile(keystore_path):
            keystore = keystore_path
            ks_pass, k_alias, k_pass = keystore_pass, key_alias, key_pass
        else:
            keystore = os.path.expanduser("~/.android/debug.keystore")
            ks_pass, k_alias, k_pass = "android", "androiddebugkey", "android"
            if not os.path.isfile(keystore):
                keystore = str(Path(tmpdir) / "debug.keystore")
                subprocess.run(
                    [
                        "keytool",
                        "-genkey",
                        "-v",
                        "-keystore",
                        keystore,
                        "-alias",
                        k_alias,
                        "-keyalg",
                        "RSA",
                        "-keysize",
                        "2048",
                        "-validity",
                        "10000",
                        "-storepass",
                        ks_pass,
                        "-keypass",
                        k_pass,
                        "-dname",
                        "CN=Android Debug,O=Android,C=US",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

        out_path = Path(output_apk).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                apksigner,
                "sign",
                "--v4-signing-enabled",
                "false",
                "--ks",
                keystore,
                "--ks-pass",
                f"pass:{ks_pass}",
                "--ks-key-alias",
                k_alias,
                "--key-pass",
                f"pass:{k_pass}",
                "--out",
                str(out_path),
                str(aligned_apk),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    print(f"[✓] RRO APK built: {out_path}")
    return str(out_path)


def package_magisk_module(
    apk_path,
    output_zip,
    module_id="pointer_replacer_rro",
    module_name="Pointer Replacer RRO",
    author="thesandipv",
    version="v2.0",
    version_code=2,
):
    out_zip = Path(output_zip).resolve()
    out_zip.parent.mkdir(parents=True, exist_ok=True)

    module_prop = f"""id={module_id}
name={module_name}
version={version}
versionCode={version_code}
author={author}
description=Magisk Implementation of Pointer Replacer RRO Overlay
"""

    customize_sh = """SKIPUNZIP=0

ui_print "****************************************"
ui_print "*        Allusive RRO Overlay          *"
ui_print "****************************************"
ui_print "- Target: Android System Framework (android)"
ui_print "- Installing RRO overlay to /system/vendor/overlay"

# Set permissions
set_perm_recursive "$MODPATH/system" 0 0 0755 0644

ui_print "- Overlay deployed successfully."
ui_print " "
ui_print "TIP: Enable Developer Options -> 'Show taps' to see your new touch pointer!"
ui_print "****************************************"
"""

    dummy_script = "#MAGISK\n"
    dummy_binary = "#!/system/bin/sh\n"

    with zipfile.ZipFile(str(out_zip), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("module.prop", module_prop)
        zf.writestr("customize.sh", customize_sh)
        zf.writestr("META-INF/com/google/android/updater-script", dummy_script)
        zf.writestr("META-INF/com/google/android/update-binary", dummy_binary)
        zf.write(apk_path, "system/vendor/overlay/allusive_rro.apk")

    print(f"[✓] Magisk Module ZIP packaged: {out_zip}")
    return str(out_zip)


def main():
    parser = argparse.ArgumentParser(
        description="Android RRO APK & Magisk Module Builder"
    )
    parser.add_argument(
        "--image", "-i", type=str, default=None, help="Path to pointer PNG image"
    )
    parser.add_argument(
        "--style",
        "-s",
        choices=[
            "glow_cyan",
            "glow_purple",
            "glow_red",
            "glow_amber",
            "minimal",
            "crosshair",
        ],
        default="glow_cyan",
        help="Preset style",
    )
    parser.add_argument(
        "--color", "-c", type=str, default=None, help="Custom hex color (e.g. #00E5FF)"
    )
    parser.add_argument(
        "--package",
        "-p",
        type=str,
        default="com.afterroot.allusive_rro",
        help="Overlay package name",
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        default="android",
        help="Target package name (default: android)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="build/allusive_rro.apk",
        help="Output APK file path",
    )
    parser.add_argument(
        "--magisk-zip",
        "-m",
        type=str,
        default=None,
        help="Optional output path for flashable Magisk Module zip",
    )
    parser.add_argument(
        "--module-name",
        type=str,
        default="Pointer Replacer RRO",
        help="Magisk module display name",
    )
    parser.add_argument("--priority", type=int, default=99, help="Overlay priority")
    parser.add_argument(
        "--batch-dir",
        type=str,
        default=None,
        help="Build RRO APKs for all PNGs in a directory",
    )
    args = parser.parse_args()

    if args.batch_dir:
        batch_dir = Path(args.batch_dir)
        if not batch_dir.is_dir():
            print(f"[!] Error: {args.batch_dir} is not a directory")
            sys.exit(1)
        out_dir = (
            Path(args.output).parent
            if args.output.endswith(".apk")
            else Path(args.output)
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        images = list(batch_dir.glob("*.png"))
        print(f"[*] Found {len(images)} images in {batch_dir}")
        for img_path in images:
            apk_name = f"RRO_{img_path.stem}.apk"
            out_apk = out_dir / apk_name
            build_rro(
                image_path=str(img_path),
                package_name=args.package,
                target_package=args.target,
                output_apk=str(out_apk),
                priority=args.priority,
            )
            if args.magisk_zip:
                zip_name = f"{img_path.stem}_Magisk.zip"
                package_magisk_module(
                    str(out_apk),
                    str(out_dir / zip_name),
                    module_name=f"Pointer - {img_path.stem}",
                )
    else:
        apk_path = build_rro(
            image_path=args.image,
            style=args.style,
            color=args.color,
            package_name=args.package,
            target_package=args.target,
            output_apk=args.output,
            priority=args.priority,
        )
        if args.magisk_zip:
            package_magisk_module(
                apk_path, args.magisk_zip, module_name=args.module_name
            )


if __name__ == "__main__":
    main()
