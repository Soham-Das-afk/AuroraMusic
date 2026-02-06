import discord
from discord.ext import commands
import logging

class GeneralCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="cleanup")
    @commands.has_permissions(administrator=True)
    async def cleanup_prefix(self, ctx, delete_channel: bool = True):
        """
        Legacy prefix command for cleanup. Defers to the slash command.
        This is a fallback and may be removed in a future version.
        """
        logging.info(f"Redirecting legacy cleanup command from {ctx.author}")
        
        # Find the slash command
        slash_command = self.bot.tree.get_command("cleanup")
        
        if slash_command:
            # Create a mock interaction
            try:
                # This is a bit of a hack to invoke the slash command logic
                # It's not a perfect interaction object, but it's enough for the cleanup command
                interaction = await self.create_mock_interaction(ctx)
                
                # Directly call the slash command's callback
                await slash_command.callback(interaction, delete_channel=delete_channel)
            except Exception as e:
                logging.error(f"Error redirecting legacy cleanup command: {e}")
                await ctx.send("An error occurred while trying to run the cleanup command.", delete_after=10)
        else:
            await ctx.send("Could not find the cleanup slash command.", delete_after=10)

    async def create_mock_interaction(self, ctx):
        """Creates a mock Interaction object from a Context object."""
        
        # This is a simplified mock. It might need more attributes depending on what the
        # slash command's callback expects.
        class MockResponse:
            def __init__(self, interaction):
                self._interaction = interaction

            async def defer(self, ephemeral=False):
                self._interaction._deferred = True
                pass

        class MockFollowup:
            def __init__(self, interaction):
                self._interaction = interaction

            async def send(self, content=None, embed=None, ephemeral=False):
                await self._interaction.ctx.send(content or (embed.description if embed else ""), delete_after=10 if ephemeral else None)

        class MockInteraction:
            def __init__(self, ctx):
                self.ctx = ctx
                self.guild = ctx.guild
                self.user = ctx.author
                self.channel = ctx.channel
                self.client = ctx.bot
                self._deferred = False
                self._responded = False
                self.response = MockResponse(self)
                self.followup = MockFollowup(self)

        return MockInteraction(ctx)

async def setup(bot):
    await bot.add_cog(GeneralCog(bot))
