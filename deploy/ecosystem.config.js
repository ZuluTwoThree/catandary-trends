// PM2 process configuration for Catandary Trends
module.exports = {
  apps: [
    {
      name: "catandary-trends",
      cwd: "./frontend",
      script: "node_modules/.bin/next",
      args: "start -p 3001",
      env: {
        NODE_ENV: "production",
        DATABASE_PATH: "../data/catandary.db",
      },
      instances: 1,
      autorestart: true,
      max_memory_restart: "500M",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};
