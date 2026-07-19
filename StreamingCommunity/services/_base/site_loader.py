# 01.10.25 

import os
import sys
import glob
import importlib
from typing import Dict


# External import
from rich.console import Console


# Internal utilites
from StreamingCommunity.setup import get_is_binary_installation


# Variable
console = Console()
folder_name = "services"


class LazySearchModule:
    def __init__(self, module_name: str, indice: int, use_for: str = None):
        """
        Lazy loader for a search module.

        Args:
            module_name: Name of the site module (e.g., 'streamingcommunity')
            indice: Sort index for the module
            use_for: Content types this module supports
        """
        self.module_name = module_name
        self.indice = indice
        self._module = None
        self._search_func = None
        self._use_for = use_for
    
    def _load_module(self):
        """Load the module on first access."""
        if self._module is None:
            try:
                self._module = importlib.import_module(
                    f'StreamingCommunity.{folder_name}.{self.module_name}'
                )
                self._search_func = getattr(self._module, 'search')
                self._use_for = getattr(self._module, '_useFor')
            except Exception as e:
                console.print(f"[red]Failed to load module {self.module_name}: {str(e)}")
                raise
    
    def __call__(self, *args, **kwargs):
        """Execute search function when called.
        
        Args:
            *args: Positional arguments to pass to search function
            **kwargs: Keyword arguments to pass to search function
            
        Returns:
            Result from the search function
        """
        self._load_module()
        return self._search_func(*args, **kwargs)
    
    @property
    def use_for(self):
        """Get _useFor attribute (loads module if needed).
        
        Returns:
            List of content types this module supports
        """
        if self._use_for is None:
            self._load_module()

        return self._use_for
    
    def __getitem__(self, index: int):
        """Support tuple unpacking: func, use_for = loaded_functions['name'].
        
        Args:
            index: Index to access (0 for function, 1 for use_for)
            
        Returns:
            Self (as callable) for index 0, use_for for index 1
        """
        if index == 0:
            return self
        elif index == 1:
            return self.use_for
        
        raise IndexError("LazySearchModule only supports indices 0 and 1")


def _load_sites_from_manifest() -> Dict[str, tuple]:
    """Load site metadata from Conf/sites.json (generated at build time for frozen builds).
    
    Returns:
        Dictionary mapping module_name to (indice, use_for) tuple
    """
    import json

    if get_is_binary_installation():
        manifest_path = os.path.join(os.path.dirname(sys.executable), 'Conf', 'sites.json')
    else:
        manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', '..', 'Conf', 'sites.json')

    if not os.path.exists(manifest_path):
        return None

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {name: (info['indice'], info.get('use_for')) for name, info in data.items()}
    except Exception as e:
        console.print(f"[yellow]Warning: Could not read sites manifest: {str(e)}")
        return None


def _discover_sites_from_files(base_path: str) -> list:
    """Discover sites by reading __init__.py files (development mode).
    
    Returns:
        List of (module_name, indice, use_for) tuples
    """
    modules_metadata = []
    for init_file in glob.glob(os.path.join(base_path, '*', '__init__.py')):
        module_name = os.path.basename(os.path.dirname(init_file))
        if module_name.startswith('_'):
            continue
        
        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            indice = None
            use_for = None
            for line in content.split('\n'):
                line = line.strip()
                if not indice and (line.startswith('indice =') or line.startswith('indice=')):
                    try:
                        indice = int(line.split('=')[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif not use_for and (line.startswith('_useFor =') or line.startswith('_useFor=')):
                    try:
                        use_for = line.split('=')[1].strip().strip('"').strip("'")
                    except IndexError:
                        pass
                
                if indice is not None and use_for is not None:
                    break
            
            if indice is not None:
                modules_metadata.append((module_name, indice, use_for))
                
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read metadata from {module_name}: {str(e)}")
    
    return modules_metadata


def load_search_functions() -> Dict[str, LazySearchModule]:
    """Load and return all available search functions from site modules.
    
    Returns:
        Dictionary mapping '{module_name}_search' to LazySearchModule instances
    """
    loaded_functions = {}
    
    # Try manifest first (works in both frozen and dev mode)
    manifest = _load_sites_from_manifest()
    
    if manifest is not None:
        # Use manifest data
        modules_metadata = [(name, info[0], info[1]) for name, info in manifest.items()]
    else:
        # Fall back to file discovery (development mode)
        base_path = os.path.dirname(os.path.dirname(__file__))
        modules_metadata = _discover_sites_from_files(base_path)
    
    # Sort by index and create lazy loaders with consecutive indices
    sorted_modules = sorted(modules_metadata, key=lambda x: x[1])
    for new_indice, (module_name, old_indice, use_for) in enumerate(sorted_modules):
        loaded_functions[f'{module_name}_search'] = LazySearchModule(module_name, new_indice, use_for)

        # Skip writing indices in frozen mode (sys._MEIPASS is read-only)
        if get_is_binary_installation():
            continue

        # Update indice in __init__.py for each module only if changed
        if new_indice == old_indice:
            continue

        base_path = os.path.dirname(os.path.dirname(__file__))
        init_file = os.path.join(base_path, module_name, '__init__.py')
        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(init_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip().startswith('indice =') or line.strip().startswith('indice='):
                        f.write(f'indice = {new_indice}\n')
                    else:
                        f.write(line)
                        
        except Exception as e:
            console.print(f"[yellow]Warning: Could not update indice in {module_name}: {str(e)}")

    return loaded_functions


def get_folder_name() -> str:
    """Get the folder name where site modules are located.
    
    Returns:
        The folder name as a string
    """
    return folder_name