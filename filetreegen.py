import os

def print_tree(root, indent="", exclude={'__pycache__', '.git', 'venv'}):
    entries = sorted(os.listdir(root))
    for i, entry in enumerate(entries):
        path = os.path.join(root, entry)
        if entry in exclude:
            continue
        connector = "└── " if i == len(entries) - 1 else "├── "
        print(indent + connector + entry)
        if os.path.isdir(path):
            extension = "    " if i == len(entries) - 1 else "│   "
            print_tree(path, indent + extension, exclude)

print_tree(".")