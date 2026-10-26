"""Agent model routes: external APIs, explicitly selected network servers and CLIs."""
import json
from pathlib import Path
import shutil

CLI_PROVIDERS={'gemini_cli':'gemini','codex_cli':'codex','claude_cli':'claude','kilo_cli':'kilo','custom_cli':''}
NETWORK_PROVIDERS={'ollama':'http://127.0.0.1:11434/v1','network':''}


def validate_agent_model(config, *, allow_test_endpoint=False):
    from dock_twoo.brain.cloud import validate_config
    provider=config.get('provider','custom')
    if provider in CLI_PROVIDERS:
        executable=str(config.get('executable') or CLI_PROVIDERS[provider]).strip()
        if not executable or '\0' in executable:raise ValueError('Choose the CLI executable or its full path.')
        arguments=config.get('arguments',[])
        if not isinstance(arguments,list) or len(arguments)>40 or any(not isinstance(a,str) or '\0' in a or len(a)>2000 for a in arguments):
            raise ValueError('Custom CLI arguments must be an array of strings, without shell syntax.')
        model=str(config.get('model','')).strip()
        if not model:raise ValueError('Choose the CLI model ID.')
        return {**config,'provider':provider,'kind':'cli','executable':executable,'arguments':arguments,'model':model,'protocol':'openai','base_url':''}
    if provider in NETWORK_PROVIDERS:
        clean=validate_config({**config,'provider':'custom','base_url':config.get('base_url') or NETWORK_PROVIDERS[provider]},allow_network_endpoint=True)
        return {**clean,'provider':provider,'kind':'network'}
    return {**validate_config(config,allow_test_endpoint=allow_test_endpoint),'kind':'api'}


def configured(config):
    if config.get('provider') in CLI_PROVIDERS:
        executable=config.get('executable') or CLI_PROVIDERS[config['provider']]
        return bool(shutil.which(executable) or Path(executable).is_file())
    return True


def model_client(config, key):
    if config.get('provider') in CLI_PROVIDERS:
        from dock_twoo.brain.ecosystem.cli import CLIClient
        return CLIClient(config,key)
    from dock_twoo.brain.cloud import CloudClient
    return CloudClient(config,key or ('local-server' if config.get('provider') in NETWORK_PROVIDERS else ''))
