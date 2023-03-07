db.createUser(
    {
        user: "configApp",
        pwd: "**********",
        roles: [
                { role: "readWrite",
                  db: "configuration"
                }
               ]
    }
);
