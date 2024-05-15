# Node.js base image
FROM node:20.11.1-alpine

# Set the working directory inside the container
WORKDIR /app

# Copy the package.json file to /app
COPY package.json ./

# Remove node_modules and package-lock.json if they exist
RUN rm -rf node_modules package-lock.json

# Install dependencies
RUN npm install

# Copy the rest of the frontend code to /app
COPY . .

# Expose the port that the application runs on
EXPOSE 5173

# Command to run the application
CMD ["npm", "start"]
