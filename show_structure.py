import os

def print_directory_structure(startpath, exclude_list):
    for root, dirs, files in os.walk(startpath):
        # Remove excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_list]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            if f not in exclude_list:
                print(f'{subindent}{f}')

# List of files and directories to exclude
exclude_list = [
    'node_modules',
    'package.json',
    'package-lock.json',
    'yarn.lock',
    'conversations.db',
    'venv',
    '.env',
    'new_env'
]

# Run the function starting from the current directory
print_directory_structure('.', exclude_list)