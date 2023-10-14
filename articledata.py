#!/usr/bin/python

############################################## About Author #########################################
# Created by: Alsamman M. Alsamman                                                                  #
# Emails: smahmoud [at] ageri.sci.eg or A.Alsamman [at] cgiar.org or SammanMohammed [at] gmail.com  #
# License: MIT License - https://opensource.org/licenses/MIT                                        #
# Disclaimer: The script comes with no warranty, use at your own risk                               #
# This script is not intended for commercial use                                                    #
#####################################################################################################


from pdf2image import convert_from_path
import bibtexparser
from pylatexenc.latex2text import LatexNodes2Text
import librarydatabase
import os
import io
from PIL import Image

############################################## global variables #############################
PreviousFirstPageImage = None


############################################## pdf #########################################
#convert the first page of a pdf file to blob format
#inputs:
    # pdf_path: path to pdf file
#outputs:
    # image: first page of the pdf file in blob format
#dependencies: pdf2image
def firstpage2blob(pdf_path, resolution=30):
    # convert to lower resolution to save memory
    pages = convert_from_path(pdf_path, 30, first_page=1, last_page=1)
    pages[0].save("firstpageimage.gif", format="GIF")
    # open the image file
    with open("firstpageimage.gif", "rb") as imageFile:
        image = imageFile.read()
    return image
# convert blob to image
# inputs:
    # blob: image in blob format
# outputs:
    # image: image in PIL format
def blob2image(blob):
    image = Image.open(io.BytesIO(blob))
    return image
############################################## bibtex #########################################

# read bibtex file and return a list of articles
# inputs:
    # bibtexFile: path to bibtex file
# outputs:
    # bib_database.entries: list of articles
# dependencies: bibtexparser
def read_bibfile(bibtexFile):
    bib_database = []
    bibtextfile = open(bibtexFile, 'r')
    # split the file into articles
    bibtext = bibtextfile.read().split('@')
    # add @ to the beginning of each article
    bibtext = ['@' + x for x in bibtext]
    # parse each article
    for i in range(len(bibtext)):
        bib=bibtexparser.loads(bibtext[i]).entries
        # if not empty
        if bib:
            bib=bib[0]
            # remove latex format
            for key in bib.keys():
                bib[key]=LatexNodes2Text().latex_to_text(bib[key])
            # bib['bibtext']=bibtext[i] will generate errors in the database
            # add to the list
            bib_database.append(bib)
    return bib_database

# def latextotext(latex):
#     return LatexNodes2Text().latex_to_text(latex)
############################################## Show Info #########################################
# format article info to string for display
def ArticleInfo2Restuct(libcon, ArticleKey):
        global PreviousFirstPageImage
        #         # delete the previous image
        if PreviousFirstPageImage and os.path.exists(PreviousFirstPageImage):
            os.remove(PreviousFirstPageImage)

        # get article info from database
        ArticleDatabaseInfo = librarydatabase.getArticleInfoByIDfromMainTable(libcon, ArticleKey)
        # check if the article exists
        if not ArticleDatabaseInfo:
            return None

        # get first page image
        firstpageimage  = librarydatabase.getFirstPageImage(libcon, ArticleKey)
        firstpageimagePath=""
        if firstpageimage:
            # to image
            firstpageimage = blob2image(firstpageimage)
            # save to temporary file
            firstpageimage.save(ArticleKey+ ".gif")
            firstpageimage.close()
            firstpageimagePath = os.path.abspath(ArticleKey+ ".gif")
            # change the global variable
            PreviousFirstPageImage = firstpageimagePath
        
        # format the article info
        # use restuctured text format
        ArticleInfo= '''=================\n''' + ArticleDatabaseInfo["title"] + '''\n================='''
        ArticleInfo += '''
:ArticleKey: ''' + ArticleKey + ''' '''
        ArticleInfo+= '''
:Authors: ''' + ArticleDatabaseInfo["author"] + ''' '''
        ArticleInfo+= '''
:Year: ''' + str(ArticleDatabaseInfo["year"]) + ''' '''
        ArticleInfo+= '''
:Journal: ''' + ArticleDatabaseInfo["journal"] + ''' '''
        if len(ArticleDatabaseInfo["url"]) > 0:
            ArticleInfo+= '''
:URL: ''' + ArticleDatabaseInfo["url"] + ''' '''
        if len(ArticleDatabaseInfo["folderpath"]) > 0:
            ArticleInfo+= '''
:FolderPath: ''' + ArticleDatabaseInfo["folderpath"] + ''' '''
        if len(ArticleDatabaseInfo["keywords"]) > 0:
            ArticleInfo+= '''
:Keywords: ''' + ArticleDatabaseInfo["keywords"]+ ''' '''
            # taggroups
        if len(ArticleDatabaseInfo["taggroups"]) > 0:
            ArticleInfo+= '''
:TagGroups: ''' + "\n\t".join(ArticleDatabaseInfo["taggroups"].split(',')) + ''' '''
        if len(ArticleDatabaseInfo["abstract"]) > 0:
            ArticleInfo+= '''
:Abstract: ''' + ArticleDatabaseInfo["abstract"] + ''' '''
            
        # get comments from subtable
        comments = librarydatabase.getArticleValuesforKeyInSubTable(libcon, 'comment', ArticleKey)
        if len(comments) > 0:
            ArticleInfo+= '''
:comments: ''' + FormatMultipleLines(comments) + ''' '''
        if firstpageimagePath != "":
            ArticleInfo+= '''
.. figure:: ''' + firstpageimagePath + '''
            :width: 300'''
            # delete the temporary file
        return ArticleInfo


def FormatMultipleLines(text, max_words_per_line=40):
    # convert line to 40 words per line
    text = text.split(" ")
    text = [text[i:i+max_words_per_line] for i in range(0, len(text), max_words_per_line)]
    text = "\n".join([" ".join(line) for line in text])
    return text