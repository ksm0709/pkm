import os
from pkm.config import get_vault_context
from unittest.mock import patch

with patch('pkm.config.get_local_config_vault', return_value=None), \
     patch.dict(os.environ, {}, clear=True), \
     patch('pkm.config.get_git_vault_name', return_value='my-repo'), \
     patch('pkm.config.get_vaults_root') as mock_root, \
     patch('pkm.config.load_config', return_value={'defaults': {'vault': 'global-vault'}}), \
     patch('pkm.config.discover_vaults', return_value=['global-vault']):
    
    # Mock that the git vault directory does NOT exist
    mock_root.return_value.__truediv__.return_value.is_dir.return_value = False
    mock_root.return_value.__truediv__.return_value.exists.return_value = False
    
    try:
        vault, source = get_vault_context()
        print(f"Success: {vault.name} from {source}")
    except Exception as e:
        print(f"Error: {e}")
