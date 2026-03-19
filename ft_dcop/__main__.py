if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        raise ValueError("Please provide a command line argument: 'simulation'")

    mode = sys.argv.pop(1)
    if mode != "simulation":
        raise ValueError("Invalid command line argument: 'simulation'")

    from .run.simulation import main

    main(sys.argv)
