# FleetFlow — First-Installation Bootstrap (SEC-001)

FleetFlow no longer seeds any default user or organisation at startup. Ordinary
application startup never creates, resets, disables or modifies a user. On a
brand-new installation you create the first administrator once, manually, with
the bootstrap command below.

## Exact command

Run from the backend directory with the application environment loaded
(`MONGO_URL` and `DB_NAME` must point at the target database — the same
`backend/.env` the app uses):

```bash
cd /app/backend
python -m bootstrap create-admin
```

## Required interactive inputs

The command prompts for each value; there are **no defaults**:

1. Organisation name
2. Admin username (3–40 chars: letters, numbers, `.`, `_`, `-`)
3. Admin email (must be a valid address)
4. Admin full name
5. Admin password — entered hidden and confirmed (asked twice, never echoed)

Validation mirrors the existing self-registration rules, including the minimum
password length of 8 characters. There is no default password.

## Example interaction (placeholders only)

```
$ python -m bootstrap create-admin
Organisation name: <YOUR ORG NAME>
Admin username: <admin-username>
Admin email: <admin@example.com>
Admin full name: <Full Name>
Admin password: ********           # hidden
Repeat for confirmation: ********  # hidden
First administrator created.
  Organisation : <YOUR ORG NAME> (org-xxxxxxxx-...)
  Username     : <admin-username>
  Email        : <admin@example.com>
  Role         : org_admin
You can now log in with the password you just entered.
```

The password is never printed, returned, logged, or included in any error
message.

## Optional automation (approved environment variables)

For non-interactive provisioning, supply every value via environment variables
and pass `--non-interactive`:

```bash
FLEETFLOW_BOOTSTRAP_ORG_NAME="<YOUR ORG NAME>" \
FLEETFLOW_BOOTSTRAP_USERNAME="<admin-username>" \
FLEETFLOW_BOOTSTRAP_EMAIL="<admin@example.com>" \
FLEETFLOW_BOOTSTRAP_FULL_NAME="<Full Name>" \
FLEETFLOW_BOOTSTRAP_PASSWORD="<strong-password>" \
python -m bootstrap create-admin --non-interactive
```

- There are **no fallback credentials**. If any required variable is missing the
  command fails safely (non-zero exit) and names only the missing variable(s).
- Secret values are never printed. Prefer a secrets manager over shell history;
  the password is deliberately **not** accepted as a command-line argument.

## Behaviour when users already exist

The command refuses if the database contains **any** user (it counts all users,
not just a matching username or email):

```
Refusing to bootstrap: the database already contains N user(s). The first admin
can only be created on a completely new installation. No account was modified.
```

Running it a second time is therefore non-destructive: it never resets,
updates, disables or deletes any existing account or organisation. This includes
the case where the only existing account is a demo user — bootstrap still
refuses.

## Fresh-installation sequence

1. Provision the database and object storage; set `MONGO_URL`, `DB_NAME` (and
   other app env) in `backend/.env`.
2. Start the backend at least once (creates indexes and runs idempotent
   migrations; it does **not** create any user or organisation).
3. Run `python -m bootstrap create-admin` and enter the organisation and admin
   details.
4. Log in through the normal login screen with the credentials you just set.
5. Create additional users from the in-app User Management screen.

## Demo remains separate

The public demo is unchanged and independent of bootstrap:

- The demo button and `POST /api/demo/enter` still work.
- Demo users are lazily seeded on first demo entry, in the isolated
  `org-fleetflow-demo` organisation, with random passwords and `is_demo: true`.
- Production bootstrap never creates demo users, and entering the demo never
  creates a production administrator.

## Rollback considerations

- Bootstrap only ever **inserts** the first organisation and its `org_admin`; it
  never modifies existing data. If the user insert fails, the just-created
  organisation is rolled back so no half-provisioned tenant remains.
- To undo a bootstrap on a truly fresh install, delete the created `org_admin`
  and its organisation directly in the database, then re-run the command. (On a
  populated database bootstrap will already have refused, so there is nothing to
  roll back.)
- This command performs no credential rotation or session revocation for
  existing accounts — those remain separate operational tasks.
