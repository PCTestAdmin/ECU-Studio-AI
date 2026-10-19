"""Application entrypoint, also used by the inspectable portable interpreter."""
import sys

if __name__ == "__main__":
    try:
        from ecu_studio.main import main
        code=main()
    except Exception:
        import traceback
        from pathlib import Path
        details=traceback.format_exc()
        if len(sys.argv)==3 and sys.argv[1]=='--smoke-test':
            destination=Path(sys.argv[2]);destination.mkdir(parents=True,exist_ok=True)
            (destination/'smoke-error.txt').write_text(details,encoding='utf-8')
        else:
            import os
            destination=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'ECUStudioAI'/'startup-error.txt'
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(details,encoding='utf-8')
            if os.name=='nt':
                import ctypes
                ctypes.windll.user32.MessageBoxW(None,'Details: '+str(destination),'ECU Studio AI: Startfehler',16)
        code=1
    raise SystemExit(code)
