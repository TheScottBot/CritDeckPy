# Security

This file is completed when the bot is packaged for deployment.

## Trust boundary

Discord interaction options and backup prefix message content are untrusted.
The prefix surface needs the privileged message content intent, which is
requested explicitly and stated in the startup log. The bot token is a secret
and is never logged or committed.

## Accepted risks

To be stated by the author in their own words before release. Carried over from
the Go bot so far: deck state lives in memory only and is lost on restart, deliberately,
because restart is the author's full reset.

## Limitations

To be stated before release.
