from typing import Optional
from tortoise.exceptions import OperationalError
from database.models import Filterlist
import discord
from discord.ext.commands import BadArgument, Cog, Context, command, has_any_role
import constants
from Bronn import Bot
from constants import Colours
from log import get_logger
from utils.paginator import LinePaginator


log = get_logger(__name__)


class Filters(Cog):
    """Commands for blacklisting and whitelisting things."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.synced_guilds: list = []

    @command(name="whitelist", aliases=("allowlist", "allow", "al", "wl"))
    async def whitelist(
        self,
        ctx: Context,
        file_type: str,
        comment: Optional[str] = None,
        allow: bool = True,
    ) -> None:

        if ctx.guild.id not in self.synced_guilds:
            await self.bot.cache_filter_list_data(ctx)
            self.synced_guilds.append(ctx.guild.id)

        # let's make sure it has a leading dot.
        if not file_type.startswith("."):
            file_type = f".{file_type}"

        # Try to add the item to the database
        log.trace(f"Trying to set {allow} to the {file_type} file")
        try:
            if await Filterlist.exists(type=file_type, guild=ctx.guild.id, allowed=allow):
                await ctx.message.add_reaction("✅")
                await ctx.reply("This extension is already whitelisted.")
            else:
                if await Filterlist.update_or_create(
                    type=file_type,
                    guild_id=ctx.guild.id,
                    allowed=allow,
                    comment=comment,
                ):
                    item = {"type": file_type, "guild_id": ctx.guild.id, "allowed": allow, "comment": comment}
                    self.bot.insert_item_into_filter_list_cache(item)
                    await ctx.message.add_reaction("✅")
                    await ctx.reply(f"File `{file_type}` whitelisted.")
                else:
                    await ctx.message.add_reaction("❌")
                    log.debug(
                        f"{ctx.author} tried to add filetype to whitelist, but update_or_create() returned False. "
                    )
        except OperationalError:
            await ctx.message.add_reaction("❌")
            log.debug(f"{ctx.author} tried to add filetype to whitelist, but tortoise returned a operational error. ")
            raise BadArgument(f"Unable to add the {file_type} to the whitelist. " "Check args and variables")

    @command(name="blacklist", aliases=("denylist", "deny", "bl", "dl"))
    async def blacklist(
        self,
        ctx: Context,
        file_type: str,
        comment: Optional[str] = None,
        allow: bool = False,
    ) -> None:
        """Add a file type to the blacklist, remove it from whitelist if needed."""

        # check if guild has cached files, otherwise get it from database
        if ctx.guild.id not in self.synced_guilds:
            await self.bot.cache_filter_list_data(ctx)
            self.synced_guilds.append(ctx.guild.id)

        # assert it has a leading dot.
        if not file_type.startswith("."):
            file_type = f".{file_type}"

        # Find the file in the cache
        log.trace(f"Trying to blacklist the {file_type}")
        item = self.bot.filter_list_cache[f"{ctx.guild.id}"].get(file_type)

        try:
            # if in cache and not blacklisted, modify it
            if item is not None and item["allow"]:
                revertbool = await Filterlist.get(type=file_type, guild=ctx.guild.id, allowed=True)
                await revertbool.revertit(allow)

            elif item is None:  # if None, create it
                await Filterlist.create(
                    type=file_type,
                    guild_id=ctx.guild.id,
                    allowed=allow,
                    comment=comment,
                )
            else:  # if already blacklisted, pass
                pass

            # create dict from passes args, and store it in the cachelist
            item = {"type": file_type, "guild_id": ctx.guild.id, "allowed": allow, "comment": comment}
            self.bot.insert_item_into_filter_list_cache(item)
            await ctx.message.add_reaction("✅")
            await ctx.reply(f"File `{file_type}` blacklisted.")
        except Exception:
            await ctx.message.add_reaction("❌")
            log.debug(
                f"{ctx.author} tried to add filetype to the blacklist, but tortoise returned a operational error. "
            )
            raise BadArgument(f"Unable to add the {file_type} to the blacklist. Check args and variables")

    @command(name="filterlist", aliases=("filelist", "fl", "fetch"))
    async def _list_all_data(self, ctx: Context, allowed: bool) -> None:
        """Paginate and display all items in the filterlist."""

        if ctx.guild.id not in self.synced_guilds:
            await self.bot.cache_filter_list_data(ctx)
            self.synced_guilds.append(ctx.guild.id)

        # Return only files that match the passed 'allowed: bool'
        result = [k for k, v in self.bot.filter_list_cache[f"{ctx.guild.id}"].items() if v["allow"] == allowed]

        # Build a list of lines we want to show in the paginator
        lines = []
        for content, metadata in result:
            line = f"• `{content}`"

            if comment := metadata.get("comment"):
                line += f" - {comment}"

            lines.append(line)
        lines = sorted(lines)

        # Build the embed, change title and color based on passed 'allowed: bool'
        if allowed is False:
            embed = discord.Embed(title=f"{ctx.guild} latest Blacklist", colour=Colours.error)
        else:
            embed = discord.Embed(title=f"{ctx.guild} latest Whitelist", colour=Colours.blue)

        log.trace(f"Trying to list {len(result)} items from the {ctx.guild} Filterlist")

        if result:
            await LinePaginator.paginate(lines, ctx, embed, max_lines=15, empty=False)
        else:
            embed.description = "Hmmm, seems like there's nothing here yet."
            await ctx.send(embed=embed)
            await ctx.message.add_reaction("❌")

    @command(name="synclist", aliases=("sl",))
    async def _sync_data(self, ctx: Context) -> None:
        """Syncs the filterlists with the database."""
        try:
            log.trace("Attempting to sync FilterList cache with data from the Database.")
            await self.bot.cache_filter_list_data(ctx)
            await ctx.message.add_reaction("✅")
        except OperationalError as e:
            log.debug(
                f"{ctx.author} tried to sync FilterList cache data but the Database raised an unexpected error: {e}"
            )
            await ctx.message.add_reaction("❌")

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*constants.MODERATION_ROLES).predicate(ctx)


def setup(bot: Bot) -> None:
    """Load the FilterLists cog."""
    bot.add_cog(Filters(bot))
