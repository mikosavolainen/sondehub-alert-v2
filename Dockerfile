# Use an official Node.js runtime as a parent image
FROM node:18-alpine

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy package.json and package-lock.json (if available)
COPY package*.json ./

# Install app dependencies
RUN npm install

# Bundle app source
COPY . .

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN adduser -D myuser && chown -R myuser:myuser /usr/src/app
USER myuser

# Define the command to run your app
CMD [ "node", "index.js" ]
