from typing import List, Callable

# Assuming each imported command function has the same signature
# You may need to adjust the Callable type based on actual function signatures
CommandFunction = Callable[..., None]

upload_dir: CommandFunction
make: CommandFunction
migrate: CommandFunction
sync: CommandFunction
regen_derived: CommandFunction

commands: List[CommandFunction]
