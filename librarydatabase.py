#!/usr/bin/env python

############################################## About Author #########################################
# Created by: Alsamman M. Alsamman                                                                  #
# Emails: smahmoud [at] ageri.sci.eg or A.Alsamman [at] cgiar.org or SammanMohammed [at] gmail.com  #
# License: MIT License - https://opensource.org/licenses/MIT                                        #
# Disclaimer: The script comes with no warranty, use at your own risk                               #
# This script is not commercial use and the auhtor has all rights reserved if used commercially     #
#####################################################################################################

# Module for database connection and queries
import sqlite3
import datetime
import os
import articledata

# create a connection to the database
# inputs:
    # db_file: Database file name
# dependencies: sqlite3, os
# outputs:
    # conn: Connection object or None
def create_connection(db_file):
    # Connect to database
    conn = sqlite3.connect(db_file)
    return conn

def getSystemPathSeparator():
    # if windows
    if os.name == 'nt':
        return '\\'
    # if linux
    return '/'
def initializeLibrary(dbFileName, dbArticlesColumnInfo, dbSubTablesInfo=None):
    # check #
    if os.path.exists(dbFileName):
        print('Database file already exists')
        return
    if not dbFileName.endswith('.db'):
        dbFileName += '.db'
    # Connect to database
    libcon = create_connection(dbFileName)
    # Create main table
    createArticlesTable(libcon, dbArticlesColumnInfo)
    # Create library properties table
    createLibraryPropertiesTable(libcon)
    # insert default library properties
    defaultLibraryProperties(libcon)
    # create subtables
    if dbSubTablesInfo != None:
        createSubTables(dbFileName, dbSubTablesInfo)
    # Commit changes
    libcon.commit()
    # Close connection
    libcon.close()
    return

# insert data into the database
# inputs:
    # libcon: Library connection
    # columnInfo: Dictionary list of columns in the articles table with their data types {'TableName1': ['ColumnName', 'DataType'],...}
# dependencies: sqlite3, os
def createArticlesTable(libcon, dbColumnInfo):
    c = libcon.cursor()
    # Create tuple of column names and data types
    column_and_type = []
    for key, value in dbColumnInfo.items():
        column_and_type.append(key + ' ' + value)
    # Create main table
    c.execute('''CREATE TABLE articles
                    ''' + str(tuple(column_and_type)).replace("'", ""))
    # Commit changes
    libcon.commit()
    return

# create a table in the database
# inputs:
    # dbFileName: Database file name
    # TableInfo: Dictionary contain table names, and its column names and data type
# dependencies: sqlite3, os
def createSubTables(dbFileName, TableInfo):
    """Create a database table"""
    # check #
    if not dbFileName.endswith('.db'):
        dbFileName += '.db'
    if not os.path.exists(dbFileName):
        print('Database file does not exist')
        return
    # Connect to database
    conn = sqlite3.connect(dbFileName)
    c = conn.cursor()
    # Loop over tables
    for tableName in TableInfo.keys():
        dataType = TableInfo[tableName]
        # Create database table
        c.execute('''CREATE TABLE {} (ID text, articleData {})'''.format(tableName, dataType))
    # Commit changes
    conn.commit()
    # Close connection
    conn.close()
    



# create table for Library Properties
# inputs:
    # libcon: Library connection
def createLibraryPropertiesTable(libcon):
    c = libcon.cursor()
    # Create main table
    c.execute('''CREATE TABLE libraryproperties
                    (property text, value text)''')
    # Commit changes
    libcon.commit()
    return


##################################  insert  ################################################
# defalut library properties
# inputs:
    # libcon: Library connection
def defaultLibraryProperties(libcon):
    c = libcon.cursor()
    # Create main table
    c.execute('''INSERT INTO libraryproperties VALUES (?,?)''', ('creationdate', str(datetime.datetime.now())))
    c.execute('''INSERT INTO libraryproperties VALUES (?,?)''', ('lastmodificationdate', str(datetime.datetime.now())))
    c.execute('''INSERT INTO libraryproperties VALUES (?,?)''', ('clusteringcategory', 'keywords')) #!!
    # create image for the fisrt page of the article
    c.execute('''INSERT INTO libraryproperties VALUES (?,?)''', ('firstpageimage', 'yes'))
    # first page image resolution
    c.execute('''INSERT INTO libraryproperties VALUES (?,?)''', ('firstpageimageresolution', '30'))
    # Commit changes
    libcon.commit()
    return


def insertArticleSet2Library(libcon, articleSet, dbColumnInfo, subTablesInfo=None):
    # get library properties
    libraryProperties = getLibraryProperties(libcon)
    notInsertedArticles = []
    for article in articleSet:
        if insertArticle2Library(libcon, article, dbColumnInfo, subTablesInfo, libraryProperties) != True:
            notInsertedArticles.append(article['ID'])
    return notInsertedArticles

# insert article to the library
# inputs:
    # libcon: Library connection
    # dbColumnInfo: Dictionary list of columns in the articles table with their data types {'TableName1': ['ColumnName', 'DataType'],...}
    # articlebib: list of articles information in bibtex format
    # subTablesInfo: Dictionary contain table names, and its column names and data type
# dependencies: sqlite3, os
def insertArticle2Library(libcon, articlebib, dbColumnInfo, subTablesInfo=None, libraryProperties=None):
    # check if article already exists
    if checkArticleExistence(libcon, articlebib['ID']):
        return False
    # insert article to the main table
    insertArticleBib2MainTable(libcon, articlebib, dbColumnInfo)
    # insert article to subtables
    if subTablesInfo != None:
        for tableName in subTablesInfo.keys():
            # if it has data
            if tableName in articlebib.keys():
                insertArticleData2SubTable(libcon, articlebib[tableName], articlebib['ID'], tableName)
    if libraryProperties != None:
        firstPageImage = libraryProperties['firstpageimage']
        firstPageImageResolution = libraryProperties['firstpageimageresolution']
        # update library properties
        # if folderpath is not empty
        if firstPageImage == 'yes' and 'folderpath' in articlebib:
            # insert first page image
            insertArticle2firstPageImage(libcon, articlebib['folderpath'], articlebib['ID'], firstPageImageResolution, forceUpdate=True)
    return True

# insert data into the database from a bibtex file dictionary
# inputs:
    # libcon: Library connection
    # dbColumnInfo: Dictionary list of columns in the articles table with their data types {'TableName1': ['ColumnName', 'DataType'],...}
    # articlebib: list of articles information in bibtex format
# dependencies: sqlite3, os
def insertArticleBib2MainTable(libcon, articlebib, dbColumnInfo):
    # get column names
    dbcols = list(dbColumnInfo.keys())
    ndbcols = len(dbcols)
    # Connect to database
    c = libcon.cursor()
    # fill with empty values
    colvalues = [''] * ndbcols
    # # Loop over tables
    for i in range(ndbcols):
        if dbcols[i] in articlebib.keys():
            colvalues[i] = articlebib[dbcols[i]]
    # insert into database table
    c.execute('''INSERT INTO articles {} VALUES {}'''.format(str(tuple(dbcols)).replace("'", ""), str(tuple(colvalues))))
    # Commit changes
    libcon.commit()

# insert data into specific subtable in the database
# inputs:
    # libcon: Library connection
    # tableName: Table name
    # articleKey: Article key
    # articleData: Article data
# dependencies: sqlite3, os
def  insertArticleData2SubTable(libcon, articleData, articleKey, tableName):
    c = libcon.cursor()
    if tableName in ['taggroups', 'keywords']:
        articleData = articleData.split(',')
    if tableName == 'author':
        articleData = articleData.split('and ')
    # if data is list
    if tableName in ['author', 'taggroups', 'keywords']:
        for data in articleData:
            # insert into database table
            c.execute('''INSERT INTO {} VALUES (?,?)'''.format(tableName), (articleKey, data.strip()))
        # Commit changes
        libcon.commit()
        return
    # if data is not list
    c.execute('''INSERT INTO {} VALUES (?,?)'''.format(tableName), (articleKey, articleData))
    # Commit changes
    libcon.commit()
    return


def insertArticle2firstPageImage(libcon, folderPath, ArticleKey, firstPageImageResolution=30, forceUpdate=False):

    # check if article already exists in the first page image table
    if not forceUpdate:
        c = libcon.cursor()
        # get all articles titles
        c.execute('''SELECT ID FROM firstpageimages WHERE ID=?''', (ArticleKey,))
        data = c.fetchone()
        # convert data to a dictionary
        if data:
            return
    # get first page image resolution
    firstPageImageResolution = int(firstPageImageResolution)
    # get first folder path
    systemPathSeparator = getSystemPathSeparator()
    if not folderPath.endswith(systemPathSeparator):
        folderPath += systemPathSeparator
    # get article ID
    articleblob = articledata.firstpage2blob(folderPath + ArticleKey + '.pdf', firstPageImageResolution)
    # insert into database table
    c = libcon.cursor()
    c.execute('''INSERT INTO firstpageimages VALUES (?,?)''', (ArticleKey, articleblob))
    # Commit changes
    libcon.commit()
    return

##################################  get  ################################################

def getAllArticlesfromMainTable(libcon):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT * FROM articles''')
    data = c.fetchall()
    # get column names
    dbcols = [description[0] for description in c.description]
    # convert to list of dictionaries
    data = [{dbcols[i]:item[i] for i in range(len(dbcols))} for item in data]
    return data

def getAllArticlesfromSubTable(libcon, tableName):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT * FROM {}'''.format(tableName))
    data = c.fetchall()
    # get column names
    dbcols = [description[0] for description in c.description]
    # convert to list of dictionaries
    data = [{dbcols[i]:item[i] for i in range(len(dbcols))} for item in data]
    return data

# get article info by ID
# inputs:
    # libcon: Library connection
    # tableName: Table name
    # articleID: Article ID
def getArticleInfoByIDfromMainTable(libcon, articleID):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT * FROM articles WHERE ID=?''', (articleID,))
    data = c.fetchall()
    if not data:
        return None
    # get column names
    dbcols = [description[0] for description in c.description]
    # convert to a dictionary
    data = {dbcols[i]:data[0][i] for i in range(len(dbcols))}
    return data

# expected one result to be returned
def getArticleInfoByIDfromSubTable(libcon, tableName, articleID):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT * FROM {} WHERE ID=?'''.format(tableName), (articleID,))
    data = c.fetchall()
    if not data:
        return None
    # if more than one result is returned return error
    if len(data) > 1:
        return "Error: more than one result is returned"
    return data[0][1]
# expected more than one result to be returned
def getArticleInfoByIDfromSubTable2(libcon, tableName, articleID):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT * FROM {} WHERE ID=?'''.format(tableName), (articleID,))
    data = c.fetchall()
    if not data:
        return None
    # get column names
    dbcols = [description[0] for description in c.description]
    # convert to list and get the second item
    data = [item[1] for item in data]
    return data
# get all articles info values for specific Table form a subtable
def getArticleInfoValuesfromSubTable(libcon, tableName):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT * FROM {}'''.format(tableName))
    data = c.fetchall()
    if not data:
        return None
    # get column names
    dbcols = [description[0] for description in c.description]
    # convert to list and get the second item
    data = [item[1] for item in data]
    # delete duplicates
    data = list(set(data))
    return data
def searchArticleInfoFromLibraryMainTable(libcon, searchQuery, searchType='title'):
    # create cursor
    c = libcon.cursor()
    # get all articles titles
    c.execute('''SELECT ID FROM articles WHERE {} LIKE ?'''.format(searchType), ('%' + searchQuery + '%',))
    data = c.fetchall()
    # convert data to a dictionary
    data = [item[0] for item in data]
    # Close connection
    return data

def searchArticleInfoFromLibrarySubTable(libcon, searchQuery,  tableName='keywords'):
    # create cursor
    c = libcon.cursor()
    # get all articles titles
    c.execute('''SELECT ID FROM {} WHERE articleData LIKE ?'''.format(tableName), ('%' + searchQuery + '%',))
    data = c.fetchall()
    # convert data to a dictionary
    data = [item[0] for item in data]
    # Close connection
    return data
# get article info by ID
# inputs:
    # libcon: Library connection
    # articleID: Article ID
# dependencies: sqlite3, os
# outputs:
    # data: Article information
def getArticleKeysforValueInSubTable(libcon, tableName, value):
    # create cursor
    c = libcon.cursor() 
    # get article IDs for value
    c.execute('''SELECT ID FROM {} WHERE articleData=?'''.format(tableName), (value,))
    data = c.fetchall()
    # Commit changes
    libcon.commit()
    # Close connection
    return data


def getReplicatesByColumn(libcon, colname):
    # create cursor
    c = libcon.cursor() 
    # get article ID and column value
    c.execute('''SELECT ID, {} FROM articles'''.format(colname))
    data = c.fetchall()
    # Commit changes
    libcon.commit()
    # convert to a dictionary
    data = {item[0]:item[1] for item in data}

    # see if there are replicates by value
    seen = {}
    replicates = []
    for key, value in data.items():
        if value not in seen:
            seen[value] = key
        else:
            replicates.append(key)
    return replicates

# remove ID keys from the main table
def removeArticleKeysfromMainTable(libcon, articleIDSet):
    # create cursor
    c = libcon.cursor() 
    # get article ID and column value
    for articleID in articleIDSet:
        c.execute('''DELETE FROM articles WHERE ID=?''', (articleID,))
    # Commit changes
    libcon.commit()
    return
# remove ID keys from the sub tables
def removeArticleKeysfromSubTable(libcon, articleIDSet, tableName):
    # create cursor
    c = libcon.cursor() 
    # get article ID and column value
    for articleID in articleIDSet:
        c.execute('''DELETE FROM {} WHERE ID=?'''.format(tableName), (articleID,))
    # Commit changes
    libcon.commit()
    return

def getArticleValuesforKeySetInSubTable(libcon, tableName, keySet):
    results = {}
    for key in keySet:
        results[key] = getArticleValuesforKeyInSubTable(libcon, tableName, key)
    return results

def getArticleValuesforKeyInSubTable(libcon, tableName, key):
    # create cursor
    c = libcon.cursor() 
    # get article IDs for value
    c.execute('''SELECT articleData FROM {} WHERE ID=?'''.format(tableName), (key,))
    data = c.fetchall()
    # Commit changes
    libcon.commit()
    # unlist
    # check if empty
    if not data:
        return []
    data = data[0][0]
    # Close connection
    return data


def getValuesforColumnInMainTable(libcon, colname):
    # create cursor
    c = libcon.cursor() 
    # get article ID and column value
    c.execute('''SELECT {} FROM articles'''.format(colname))
    data = c.fetchall()
    # Commit changes
    libcon.commit()
    # Close connection
    return data

def getValuesforColumnInSubTable(libcon, tableName):
    # create cursor
    c = libcon.cursor() 
    # get article ID and column value
    c.execute('''SELECT articleData FROM {}'''.format(tableName))
    data = c.fetchall()
    # Commit changes
    libcon.commit()
    # to list 
    data = [item[0] for item in data]
    # Close connection
    return data

# get article IDs from a subtable
# inputs:
    # libcon: Library connection
    # articleID: Article ID
# dependencies: sqlite3, os
# outputs:
    # data: Article information
def getAllArticleIDsfromSubTable(libcon, tableName):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT articleData , ID  FROM {}'''.format(tableName))
    data = c.fetchall()
    # convert to a dictionary
    clusters = {}
    # initialize dictionary
    clusters = {item[0]:[] for item in data}
    for item in data:
        clusters[item[0]].append(item[1])
    return clusters

def getLibraryProperties(libcon):
    c = libcon.cursor()
    # insert into database table
    c.execute('''SELECT * FROM libraryproperties''')
    data = c.fetchall()
    # convert to a dictionary
    data = {item[0]:item[1] for item in data}
    return data


# get first page image from the database
def getFirstPageImage(libcon, articlekey):
    # create cursor
    c = libcon.cursor()
    # get all articles titles
    c.execute('''SELECT articleData FROM firstpageimages WHERE ID=?''', (articlekey,))
    data = c.fetchone()
    if not data:
        return None
    # convert data to a dictionary
    data = data[0]
    # return data
    return data

def checkArticleExistence(libcon, articleID):
    # create cursor
    c = libcon.cursor()
    # get all articles titles
    c.execute('''SELECT ID FROM articles WHERE ID=?''', (articleID,))
    data = c.fetchone()
    # convert data to a dictionary
    if data:
        return True
    return False


##################################  update  ################################################

def updateMainTableRowSet(libcon, colname, articleIDSet, articleDataSet, forceUpdate=False):
    notUpdatedArticles = []
    for i in range(len(articleIDSet)):
        updatedSuccess = updateMainTableRow(libcon, colname, articleIDSet[i], articleDataSet[i], forceUpdate)
        if not updatedSuccess:
            notUpdatedArticles.append(articleIDSet[i])
    return notUpdatedArticles

# update article in the library
# inputs:
    # libcon: Library connection
    # dbColumnInfo: Dictionary list of columns in the articles table with their data types {'TableName1': ['ColumnName', 'DataType'],...}
    # articlebib: list of articles information in bibtex format
    # subTablesInfo: Dictionary contain table names, and its column names and data type
# dependencies: sqlite3, os
def updateMainTableRow(libcon, colname, articleID, articleData, forceUpdate=False):
    # create cursor
    c = libcon.cursor()
    # get all articles titles
    c.execute('''SELECT {} FROM articles WHERE ID=?'''.format(colname), (articleID,))
    data = c.fetchone()
    # if data has value and forceUpdate is false
    if data and not forceUpdate:
        return False
    # if data has value and forceUpdate is true
    # update row
    c.execute('''UPDATE articles SET {}=? WHERE ID=?'''.format(colname), (articleData, articleID))
    # Commit changes
    libcon.commit()
    return True

def updateSubTableRowSet(libcon, tableName, articleIDSet, articleDataSet, forceUpdate=False):
    notUpdatedArticles = []
    for i in range(len(articleIDSet)):
        updatedSuccess = updateSubTableRow(libcon, tableName, articleIDSet[i], articleDataSet[i], forceUpdate)
        if not updatedSuccess:
            notUpdatedArticles.append(articleIDSet[i])
    return notUpdatedArticles

def updateSubTableRow(libcon, tableName, articleID, articleData, forceUpdate=False):
    # create cursor
    c = libcon.cursor()
    # delete information from the table
    c.execute('''DELETE FROM {} WHERE ID=?'''.format(tableName), (articleID,))
    # Commit changes
    libcon.commit()
    # insert data
    insertArticleData2SubTable(libcon, articleData, articleID, tableName)
    return True
def updateArticleInfoInSubTable(libcon, tableName, articleID, newvalues, deletedvalues=None):
    # create cursor
    c = libcon.cursor()
    # delete information from the table
    if deletedvalues != None:
        for deletedvalue in deletedvalues:
            c.execute('''DELETE FROM {} WHERE ID=? AND articleData=?'''.format(tableName), (articleID, deletedvalue))
        # Commit changes
        libcon.commit()
    # insert data
    for newvalue in newvalues:
        insertArticleData2SubTable(libcon, newvalue, articleID, tableName)
    return True
##################################  delete  ################################################
def deleteArticle(libcon, articleID, subTablesInfo=None):
    # create cursor
    c = libcon.cursor()
    # delete information from the main table
    c.execute('''DELETE FROM articles WHERE ID=?''', (articleID,))
    # Commit changes
    libcon.commit()
    # delete information from subtables
    if subTablesInfo != None:
        for tableName in subTablesInfo.keys():
            c.execute('''DELETE FROM {} WHERE ID=?'''.format(tableName), (articleID,))
        # Commit changes
        libcon.commit()
    return True