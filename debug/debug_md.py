try:
    from main import md
    print("MD initialized successfully")
    print("--- Test Mark ---")
    print(md.render("==test=="))
    print("--- Test Callout ---")
    print(md.render("> [!NOTE] Title\n> Content"))
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
