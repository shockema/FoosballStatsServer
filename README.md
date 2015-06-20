# FoosballStatsServer
Slack Integration / Web API for tracking statistics for Foosball games among players in an organization.
See this project's [wiki](https://github.com/shockema/FoosballStatsServer/wiki) for the planned roadmap.

## To install on a server: 
1.  Create a MySQL database, e.g. called "Foosball"; create the tables using `foosball.sql`.
2.  Customize the JSON in the `foosball.cfg` config file with details of your database and connection.
3.  Update the `_g_configFile` variable at the top of `statsServer.py` to point to the config file.
4.  This uses Flask for HTTP request routing.  Set up your web server (for example, NGinX with uWSGI) to point to the python code.


## To integrate with Slack:

1.  Create a Web API token for your organization if you haven't already at:  https://api.slack.com/web.
  - Add this to the "foosball.cfg" file with the "apiToken" key.

2. Create a Slack channel for the bot to post messages in.

3.  Create a custom integration:
  - Go to `http://<yourTeamDomain>.slack.com/`.
  - Click on the "Add Integration" button 
  - In the All Services list, Add the "Slash Command" configuration.
  - In the Integration Settings, make sure the URL points to your web server and includes "/slack" as the final thing, for example `https://someserver.com/foosball/slack`.
  - Leave the Method as `POST`.
  - Generate a Token there and add it to the `foosball.cfg` file with the "teamPayloadToken" key.


## Simple usage instructions:

* Use `/foosball help` for a list of commands.
* On player names...
   - Players must be added before games they participate in can be registered.
   - All player names must be unique.  We suggest you use the first part of your company email address.
   - Player names can be changed (while maintaining their statistics) using the "changePlayer" command.
