-- Opening the bell marks everything as read.
UPDATE notifications SET read = 1 WHERE read = 0;
