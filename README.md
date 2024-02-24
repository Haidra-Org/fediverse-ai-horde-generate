# Fediverse AI Horde Generator

A bot which can function on both mastodon and lemmy for generating stable diffusion images as replies via the [AI Horde](https://aihorde.net)

You can find the official implementation below

* [Lemmy](https://lemmy.dbzer0.com/u/aihorde)
* [Mastodon](https://sigmoid.social/@stablehorde_generator)

The resulting art from this bot is always crossposted to the [BotArt Lemmy community](https://lemmy.dbzer0.com/c/botart)

# Requirements

You need to fill-in your `.env` with the required variables for this bot. You can find a sample `.env_template` you can rename to `.env` to start

You will need an AI Horde account with which to request generations. Once you create an API key, ensure you contact the AI Horde moderators and request your user to become a service account. This is necessary to be able to send the usernames of the people requesting generations to the horde, which is part of the anti-abuse system.
