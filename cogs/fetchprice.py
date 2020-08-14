import discord
from discord.ext import commands
import urllib.request
import json
import datetime as DT
import statistics
import difflib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import configparser
import os
from utils import common_names, emojis


class FetchPrice(commands.Cog):
    """Cog that deals with all prices related stuffs.

    Commands:
        - prices
            Fetch current market prices from Data Project API.
            Also send plot of 7 days historical prices.
                - quick (part of prices)
                    Same as prices command but without plots (faster).

    Functions:
        - item_match(item)
            Find closest matching item name/ID of input item.
            Uses difflib.
            Returns first 4 closest match.
        - grabHistory(item)
            Get item's 7 days historical prices for all cities.
            Plots them out to 'plot.png'.
    """

    def __init__(self, client):
        self.client = client

        # Load config.ini and get configs
        currentPath = os.path.dirname(os.path.realpath(__file__))
        configs = configparser.ConfigParser()
        configs.read(os.path.dirname(currentPath) + "/config.ini")

        debugChannel = int(configs["Channels"]["debugChannelID"])
        workChannel = [
            int(ID) for ID in configs["Channels"]["workChannelID"].split(", ")
        ]
        self.debugChannel = client.get_channel(debugChannel)
        self.workChannel = workChannel

        self.onlyWork = configs["General"].getboolean("onlyWork")
        self.debug = configs["General"].getboolean("debug")

        # API URLs
        self.iconURL = "https://render.albiononline.com/v1/item/"  # + "T4_HIDE_LEVEL1@1.png?count=1&quality=1"

        # Latest
        self.apiURL = "https://www.albion-online-data.com/api/v2/stats/prices/"
        self.locationURL = "?locations=Caerleon,Lymhurst,Martlock,Bridgewatch,FortSterling,Thetford,ArthursRest,MerlynsRest,MorganasRest,BlackMarket"
        # Historical
        self.historyURL = "https://www.albion-online-data.com/api/v2/stats/charts/"
        self.historyLocationURL = "&locations=Thetford,Martlock,Caerleon,Lymhurst,Bridgewatch,FortSterling,ArthursRest,MerlynsRest,MorganasRest,BlackMarket"

        # Bot fetches data once, adds common names, and saves locally
        self.itemData = common_names.getItemsList()

    @commands.command(
        aliases=["price", "quick",]
    )
    async def prices(self, ctx, *, item):
        """Fetch current prices from Data Project API.

        - Usage: <commandPrefix> price <item name>
        - Item name can also be its ID
        - Uses difflib for item name recognition.
        - Outputs as Discord Embed with thumbnail.
        - Plots 7 days historical prices.
        """

        # Get command (price or quick)
        command = ctx.message.content.split()

        # Debug message
        if self.debug:
            await self.debugChannel.send(f"{ctx.message.content}")

        # Check if in workChannel
        if self.onlyWork:
            if ctx.channel.id not in self.workChannel:
                return

        await ctx.channel.trigger_typing()

        # difflib for input search
        itemNames, itemIDs = self.item_match(item)

        # Grab prices from full URL
        em = await self._createEmbed(itemNames[0], itemIDs[0], itemNames[1:], itemIDs[1:])

        if not any(["quick" in c.lower() for c in command[:2]]):
            # Skip plotting if command is quick
            # Trigger typing again so that user know its still loading

            await ctx.channel.trigger_typing()

            # Grab past 7 days historical prices and plot them
            self.grabHistory(itemIDs[0], itemNames[0])

            plotFile = discord.File("./plot.png", filename="plot.png")

            # Finally send the embed
            msg = await ctx.send(embed=em, file=plotFile)
        else:
            msg = await ctx.send(embed=em)

        # Add delete reaction button
        await self._addReactions(msg)

        if self.debug:
            await self.debugChannel.send(
                f"{ctx.message.content} | Matched -> {itemNames[0]} ({itemIDs[0]})"
            )

    # Error message of prices
    @prices.error
    async def prices_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please specify item.")

    def item_match(self, inputWord):
        """Find closest matching item name and ID of input item.

        - Matches both item ID (UniqueName) and item name (LocalizedNames)
        - Uses difflib.
        - Returns 4 closest match.
        """

        itemNames = []
        itemIDs = []
        jDists = []

        # Read item list
        data = self.itemData

        # Loop through each item in item.json
        # Store distance and item index of each item
        for (i, indivData) in enumerate(data):

            # Calculate distance for item ID (UniqueName)
            try:
                w1 = inputWord.lower()
                w2 = indivData["UniqueName"].lower()

                # Use difflib's SequenceMatcher
                jDist = 1 - difflib.SequenceMatcher(None, w1, w2).ratio()
                jDists.append([jDist, i])

            # If item has no 'UniqueName'
            except:
                # Max distance is 1
                jDists.append([1, i])

            # Calculate distance for item name (LocalizedNames)
            try:
                w1 = inputWord.lower()

                # Get distance for all localizations
                localDists = []
                for name in indivData["LocalizedNames"]:
                    w2 = indivData["LocalizedNames"][name].lower()

                    localDist = 1 - difflib.SequenceMatcher(None, w1, w2).ratio()
                    localDists.append(localDist)

                # Pick the closest distance as jDist
                jDist = min(localDists)
                jDists.append([jDist, i])

            # If item has no 'LocalizedNames'
            except:
                jDists.append([1, i])

            # Calculate distance using common names
            w1 = inputWord.lower()
            for cname in indivData["CommonNames"]:
                jDist = 1 - difflib.SequenceMatcher(None, w1, cname.lower()).ratio()
                jDists.append([jDist, i])
        # Sort JDists
        # Closest match has lowest distance
        jDists = sorted(jDists)

        # Get item names and IDs of first 4 closest match
        itemNames = [data[jDist[1]]["LocalizedNames"]["EN-US"] for jDist in jDists[:4]]
        itemIDs = [data[jDist[1]]["UniqueName"] for jDist in jDists[:4]]

        return itemNames, itemIDs

    def grabHistory(self, item, itemName):
        """Grab item's 7 days historical prices for all cities, and plots them.

        - Grabbed from Data Project API.
        - Plots timeseries to 'plot.png'.
        """

        # Outliers makes the plot useless, so we find and remove them
        # This function is not very effective though
        def reject_outliers(data):
            d = [abs(i - statistics.median(data)) for i in data]
            mdev = statistics.median(d)
            s = [i / mdev if mdev else 0 for i in d]
            m = 10
            indices = [i for (i, val) in enumerate(s) if val < m]

            newData = [data[i] for i in indices]

            return newData, indices

        # Find API URL for past 7 days
        # historyURL requires dates in %m-%d-%Y format
        today = DT.datetime.utcnow()
        numDays = 7
        date = (today - DT.timedelta(days=numDays)).strftime("%m-%d-%Y")
        fullURL = (
            self.historyURL
            + item
            + "?date="
            + date
            + self.historyLocationURL
            + "&time-scale=1"
        )

        # List will have 10 different indices for 10 different cities
        # The indices corresponds to this ordering of cities (Alphabetical):
        # Arthurs, BlackMarket, Bridgewatch, Caerleon, Fort Sterling, Lymhurst, Martlock, Merlyns, Morganas, Thetford
        prices_minAll = [[], [], [], [], [], [], [], [], [], []]
        timestampsAll = [[], [], [], [], [], [], [], [], [], []]
        itemCountsAll = [[], [], [], [], [], [], [], [], [], []]

        # Get price
        try:
            with urllib.request.urlopen(fullURL) as url:
                prices = json.loads(url.read().decode())

        except Exception as e:
            print(e)
            return

        else:
            for price in prices:
                if price["quality"] == 1:
                    if price["location"] == "Arthurs Rest":
                        prices_minAll[0].extend(price["data"]["prices_avg"])
                        timestampsAll[0].extend(price["data"]["timestamps"])
                        itemCountsAll[0].extend(price["data"]["item_count"])
                    elif price["location"] == "Black Market":
                        prices_minAll[1].extend(price["data"]["prices_avg"])
                        timestampsAll[1].extend(price["data"]["timestamps"])
                        itemCountsAll[1].extend(price["data"]["item_count"])
                    elif price["location"] == "Bridgewatch":
                        prices_minAll[2].extend(price["data"]["prices_avg"])
                        timestampsAll[2].extend(price["data"]["timestamps"])
                        itemCountsAll[2].extend(price["data"]["item_count"])
                    elif price["location"] == "Caerleon":
                        prices_minAll[3].extend(price["data"]["prices_avg"])
                        timestampsAll[3].extend(price["data"]["timestamps"])
                        itemCountsAll[3].extend(price["data"]["item_count"])
                    elif price["location"] == "Fort Sterling":
                        prices_minAll[4].extend(price["data"]["prices_avg"])
                        timestampsAll[4].extend(price["data"]["timestamps"])
                        itemCountsAll[4].extend(price["data"]["item_count"])
                    elif price["location"] == "Lymhurst":
                        prices_minAll[5].extend(price["data"]["prices_avg"])
                        timestampsAll[5].extend(price["data"]["timestamps"])
                        itemCountsAll[5].extend(price["data"]["item_count"])
                    elif price["location"] == "Martlock":
                        prices_minAll[6].extend(price["data"]["prices_avg"])
                        timestampsAll[6].extend(price["data"]["timestamps"])
                        itemCountsAll[6].extend(price["data"]["item_count"])
                    elif price["location"] == "Merlyns Rest":
                        prices_minAll[7].extend(price["data"]["prices_avg"])
                        timestampsAll[7].extend(price["data"]["timestamps"])
                        itemCountsAll[7].extend(price["data"]["item_count"])
                    elif price["location"] == "Morganas Rest":
                        prices_minAll[8].extend(price["data"]["prices_avg"])
                        timestampsAll[8].extend(price["data"]["timestamps"])
                        itemCountsAll[8].extend(price["data"]["item_count"])
                    elif price["location"] == "Thetford":
                        prices_minAll[9].extend(price["data"]["prices_avg"])
                        timestampsAll[9].extend(price["data"]["timestamps"])
                        itemCountsAll[9].extend(price["data"]["item_count"])

        # Parse datetime
        for (i, timestamps) in enumerate(timestampsAll):
            timestampsAll[i] = [
                DT.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
                for timestamp in timestamps
            ]

        # Reject outliers from prices data as well as their corresponding timestamps
        for (i, prices) in enumerate(prices_minAll):
            try:
                prices_minAll[i], indices = reject_outliers(prices)
                timestampsAll[i] = [timestampsAll[i][j] for j in indices]
                itemCountsAll[i] = [itemCountsAll[i][j] for j in indices]
            # Pass if prices_minAll = []
            except:
                pass

        # Plot labels and plot colors
        names = [
            "Arthur's Rest",
            "Black Market",
            "Bridgewatch",
            "Caerleon",
            "Fort Sterling",
            "Lymhurst",
            "Martlock",
            "Merlyn's Rest",
            "Morgana's Rest",
            "Thetford",
        ]
        colors = [
            "red",
            "rosybrown",
            "orange",
            "black",
            "slategrey",
            "forestgreen",
            "blue",
            "darkturquoise",
            "purple",
            "brown",
        ]
        plotOrders = [3, 2, 4, 5, 6, 9]

        # Plot the data
        plt.style.use("seaborn")
        fig, ax = plt.subplots(
            nrows=3, ncols=2, figsize=(15, 8.75), sharex=True, sharey=True
        )
        ax = ax.flatten()

        fig.suptitle(f"7 Days Sell Order Prices for {itemName} ({item})")

        fig.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.subplots_adjust(wspace=0.025, hspace=0.15)

        for j in range(6):
            # Create gridspec in each subplot
            gs = gridspec.GridSpecFromSubplotSpec(
                2, 1, subplot_spec=ax[j], height_ratios=[4, 1], hspace=0.1
            )

            # First grid is for prices
            ax0 = plt.subplot(gs[0])
            # Second grid for item counts
            if j > 0:
                ax1 = plt.subplot(gs[1], sharex=ax0, sharey=axPrev)
            else:
                ax1 = plt.subplot(gs[1], sharex=ax0)

            # Iterate over all cities and plot each one
            for (i, timestamp) in enumerate(timestampsAll):
                try:
                    # Only plot those that are in plotOrders
                    if i in plotOrders:
                        ax0.plot(
                            timestampsAll[i], prices_minAll[i], color="gray", alpha=0.3,
                        )
                # Pass if prices_minAll = []
                except:
                    pass

            # Plot the main city
            ax0.plot(
                timestampsAll[plotOrders[j]],
                prices_minAll[plotOrders[j]],
                color=colors[plotOrders[j]],
            )

            # Plot item counts
            ax1.bar(
                timestampsAll[plotOrders[j]], itemCountsAll[plotOrders[j]], width=0.04,
            )

            # Remember item counts axis for sharey
            if j == 0:
                axPrev = ax1

            # Only show axis for left and bottom
            plt.setp(ax0.get_xticklabels(), visible=False)
            if j % 2:
                plt.setp(ax0.get_yticklabels(), visible=False)
                plt.setp(ax1.get_yticklabels(), visible=False)
            else:
                ax0.set_ylabel("Silvers")
                ax1.set_ylabel("Volume")
            if j not in (4, 5):
                plt.setp(ax1.get_xticklabels(), visible=False)

            # Title and date axis
            ax0.set_title(f"{names[plotOrders[j]]}")
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))

        fig.savefig("plot.png", bbox_inches="tight")
        plt.close("all")

        return

    async def _createEmbed(self, itemName: str, itemId: str, altNames=[], altIds=[]) -> 'discord embed':
        """ Extracting embed to make consecutive calls easier"""
        fullURL = self.apiURL + itemId + self.locationURL
        with urllib.request.urlopen(fullURL) as url:
            data = json.loads(url.read().decode())

        # Create Discord embed
        em = discord.Embed(
            title=f"Current Prices for:\n**{itemName} ({itemId})**"
        )

        if data != []:
            # Extracting locations' timestamps and minimum sell order prices
            timeStringAll = []
            timeStringAllBuy = []
            locationStringAll = []
            sellPriceMinStringAll = []
            buyPriceMaxStringAll = []

            for (i, indivData) in enumerate(data):

                # Skip if no data for entry
                if indivData["sell_price_min"] == 0 and indivData["buy_price_max"] == 0:
                    continue

                # Convert timestamp to datetime format
                # And find how long ago is timestamp in seconds
                timestamp = DT.datetime.strptime(
                    indivData["sell_price_min_date"], "%Y-%m-%dT%H:%M:%S"
                )
                tdelta = DT.datetime.utcnow() - timestamp
                tdelta = DT.timedelta.total_seconds(tdelta)

                if tdelta >= 94608000:
                    timeString = "NIL"
                elif tdelta >= 3600:
                    timeString = str(round(tdelta / 3600, 1)) + " hours ago"
                elif tdelta >= 60:
                    timeString = str(round(tdelta / 60)) + " mins ago"
                else:
                    timeString = str(round(tdelta)) + " sec ago"

                timeStringAll.append(timeString)

                # Convert timestamp for max buy order price dates
                timestamp = DT.datetime.strptime(
                    indivData["buy_price_max_date"], "%Y-%m-%dT%H:%M:%S"
                )
                tdelta = DT.datetime.utcnow() - timestamp
                tdelta = DT.timedelta.total_seconds(tdelta)

                if tdelta >= 94608000:
                    timeString = "NIL"
                elif tdelta >= 3600:
                    timeString = str(round(tdelta / 3600, 1)) + " hours ago"
                elif tdelta >= 60:
                    timeString = str(round(tdelta / 60)) + " mins ago"
                else:
                    timeString = str(round(tdelta)) + " sec ago"

                timeStringAllBuy.append(timeString)

                # Put quality beside location
                try:
                    if indivData["quality"] == 0 or indivData["quality"] == 1:
                        locationString = indivData["city"]
                    elif indivData["quality"] == 2:
                        locationString = indivData["city"] + " (Good)"
                    elif indivData["quality"] == 3:
                        locationString = indivData["city"] + " (Oustanding)"
                    elif indivData["quality"] == 4:
                        locationString = indivData["city"] + " (Excellent)"
                    elif indivData["quality"] == 5:
                        locationString = indivData["city"] + " (Masterpiece)"
                # Quality not given for items without quality
                except:
                    locationString = indivData["city"]

                locationStringAll.append(locationString)

                # Getting the minimum sell order prices
                sellPriceMinStringAll.append(indivData["sell_price_min"])

                # Getting the maximum buy order prices
                buyPriceMaxStringAll.append(indivData["buy_price_max"])

            # Express in embed format
            # Basically just output list as column
            embedLocationString = ""
            embedPriceString = ""
            embedTimeString = ""
            embedPriceStringBuy = ""
            embedTimeStringBuy = ""
            embedLocationStringBuy = ""

            for (i, locationString) in enumerate(locationStringAll):
                # Don't output if no data
                if sellPriceMinStringAll[i] != 0:
                    embedLocationString += locationString + "\n"
                    embedPriceString += str(sellPriceMinStringAll[i]) + "\n"
                    embedTimeString += timeStringAll[i] + "\n"

                if buyPriceMaxStringAll[i] != 0:
                    embedLocationStringBuy += locationString + "\n"
                    embedPriceStringBuy += str(buyPriceMaxStringAll[i]) + "\n"
                    embedTimeStringBuy += timeStringAllBuy[i] + "\n"

            # Only add embeds if there are prices to show
            if embedPriceString:
                # Add the fields to Discord embed
                em.add_field(name="Locations", value=embedLocationString, inline=True)
                em.add_field(name="Min Sell Price", value=embedPriceString, inline=True)
                em.add_field(name="Last Updated", value=embedTimeString, inline=True)

            if embedPriceStringBuy:
                # Add fields for buy orders
                em.add_field(
                    name="Locations", value=embedLocationStringBuy, inline=True
                )
                em.add_field(
                    name="Max Buy Price", value=embedPriceStringBuy, inline=True
                )
                em.add_field(name="Last Updated", value=embedTimeStringBuy, inline=True)
        else:
            # No data
            nodataString = "NO DATA"
            em.add_field(
                name=f"\n{nodataString:-^60}\n",
                value="There are no data for this item.",
                inline=True,
            )

        # 'finally'
        # Next 3 closest item matches suggestions
        # Good for people if they don't remember item's name and type wrongly
        # Will add reactions based on this to make calling them easier
        if(altNames != []):
            tierEmojis = emojis.getTierEmojis()
            em.add_field(
                name="Suggestions:",
                value='\n'.join([f"{tierEmojis[i]} {altNames[i]} ({altIds[i]})" for i in range(len(altNames))]),
                inline=False,
            )

        # Adding thumbnail
        iconFullURL = self.iconURL + itemId + ".png"

        em.set_thumbnail(url=iconFullURL)

        # \u274c is a red X
        em.set_footer(text="React with \u274c to delete this post.")
        return em

    async def _addReactions(self, msg) -> None:
        # First add delete reaction
        await msg.add_reaction("\u274c")
        try:
            tierEmojis = emojis.getTierEmojis()
            for i in range(3):
                await msg.add_reaction(tierEmojis[i])
        except Exception as e:
            print(e)


def setup(client):
    client.add_cog(FetchPrice(client))
