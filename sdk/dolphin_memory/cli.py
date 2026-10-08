"""
Dolphin CLI
============
Usage:
    dolphin mcp       Run the MCP server over stdio
    dolphin daemon    start | stop | status the local memory daemon
    dolphin hook      Handle an agent hook event (reads JSON from stdin)
    dolphin graph     Open a live 3D view of the local knowledge graph
    dolphin setup     Install Ollama and pull the extraction model
    dolphin doctor    Check system health
"""

import sys

USAGE = __doc__.strip()


def main():
    """Entrypoint for the `dolphin` command."""
    # Windows consoles often can't encode the emoji used in status output
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    command = sys.argv[1] if len(sys.argv) > 1 else ""

    if command == "hook":
        from dolphin_memory.hook import main as hook_main
        sys.exit(hook_main(sys.argv[2:]))
    elif command == "daemon":
        from dolphin_memory.daemon import main as daemon_main
        sys.exit(daemon_main(sys.argv[2:]))
    elif command == "graph":
        from dolphin_memory.viewer import main as viewer_main
        sys.exit(viewer_main(sys.argv[2:]))
    elif command == "mcp":
        try:
            from dolphin_memory.mcp_server import run
        except ImportError as e:
            print(f"The MCP server needs the 'mcp' package: {e}", file=sys.stderr)
            sys.exit(1)
        run()
    elif command == "setup":
        from dolphin_memory.setup import run_setup
        run_setup()
    elif command == "doctor":
        from dolphin_memory.setup import run_doctor
        run_doctor()
    elif command in ("-h", "--help", "help"):
        print(USAGE)
    else:
        print(USAGE, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
