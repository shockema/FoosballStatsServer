USE Foosball;
GO


DROP TABLE IF EXISTS Game;
DROP TABLE IF EXISTS Player;
GO


CREATE TABLE Player (
    id INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(256) NOT NULL,
    UNIQUE INDEX index_Player_name (name)
);
GO


CREATE TABLE Game (
    id INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    timestamp DATETIME NOT NULL,
    recordedBy VARCHAR(256) NOT NULL,
    redScore INT NOT NULL,
    blackScore INT NOT NULL,
    redDefense INT NOT NULL,
    redOffense INT NOT NULL,
    blackDefense INT NOT NULL,
    blackOffense INT NOT NULL,
    FOREIGN KEY (redDefense) REFERENCES Player(id) ON UPDATE CASCADE,
    FOREIGN KEY (redOffense) REFERENCES Player(id) ON UPDATE CASCADE,
    FOREIGN KEY (blackDefense) REFERENCES Player(id) ON UPDATE CASCADE,
    FOREIGN KEY (blackOffense) REFERENCES Player(id) ON UPDATE CASCADE,
    INDEX index_Game_redDefense (redDefense),
    INDEX index_Game_redOffense (redOffense),
    INDEX index_Game_blackDefense (blackDefense),
    INDEX index_Game_blackOffense (blackOffense)
);
GO
