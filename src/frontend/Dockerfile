# Node.js base image
FROM node:20.11.1-alpine

# Set the working directory inside the container
WORKDIR /app

# Copy the package.json file to /app
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the frontend code to /app
COPY . .

# Expose the port that the application runs on
EXPOSE 5173

# Command to run the application
CMD ["npm", "start"]
