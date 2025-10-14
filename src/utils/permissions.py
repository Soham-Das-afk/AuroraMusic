def has_permission(user, required_role):
    """Check if the user has the required role."""
    return any(role.name == required_role for role in user.roles)

def is_guild_allowed(guild_id, allowed_guilds):
    """Check if the guild ID is in the list of allowed guilds."""
    return guild_id in allowed_guilds

def is_user_in_voice_channel(user):
    """Check if the user is in a voice channel."""
    return user.voice is not None

def can_use_music_commands(user, guild_id, allowed_guilds, required_role):
    """Check if the user can use music commands based on permissions."""
    return (is_guild_allowed(guild_id, allowed_guilds) and 
            is_user_in_voice_channel(user) and 
            has_permission(user, required_role))