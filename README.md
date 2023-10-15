
![SciLibra icon](SciLibra_icon.png)
# SciLibra 


## Description
SciLibra is a free and open-source software for managing scientific articles. It provides a user interface for organizing and viewing scientific articles, including features for importing articles from BibTeX files, clustering articles by different categories, and viewing article details.

## How to use SciLibra
1. Download you articles from your favorite search engine as a BibTeX and PDF files.
2. Import the BibTeX file into SciLibra.
3. Use the update path in the Action menu to update the PDF path for your article.
4. The bibtex file can contain several articles, and the PDF files can be in different folders.
6. The PDF file name should be the same as the BibTeX key.

## Example of BibTeX file

```
@article{alsamman2023alignstatplot,
  title={AlignStatPlot: An R package and online tool for robust sequence alignment statistics and innovative visualization of big data},
  author={Alsamman, Alsamman M and El Allali, Achraf and Mokhtar, Morad M and Al-Sham’aa, Khaled and Nassar, Ahmed E and Mousa, Khaled H and Kehel, Zakaria},
  journal={PloS one},
  volume={18},
  number={9},
  pages={e0291204},
  year={2023},
  publisher={Public Library of Science San Francisco, CA USA},
  taggroups = {Agricultural drainage,Artificial intelligence,Deep learning,Drainage water,Groundwater,Machine learning,Water quality},
}
```

The PDF file name should be the same as the BibTeX key, in this case, the PDF file name should be "alsamman2023alignstatplot.pdf"

### Key Features
- **Import Articles**: Effortlessly import scientific articles from BibTeX files, simplifying the process of building and maintaining your library.

- **Article Clustering**: Seamlessly categorize your articles by various criteria such as title, author, year, journal, tag groups, and keywords. This intuitive clustering system enhances your ability to locate and manage specific articles efficiently.

- **Cross-Platform**: Developed using the Kivy framework, SciLibra is designed to be a cross-platform solution. You can enjoy its functionality on both mobile and desktop devices, ensuring accessibility wherever you go.

- **Detailed Article Insights**: Dive deep into your articles by accessing detailed information and abstracts, allowing you to make informed decisions when working on your research.

### Mobile and Desktop Compatibility
SciLibra has been developed with flexibility in mind. It's not only a powerful desktop application but also a mobile-friendly tool. Whether you're on the move or at your desk, SciLibra adapts to your needs, providing a seamless experience for managing your scientific literature.

Empower yourself as a researcher or academic, stay organized, save time, and enhance your research productivity with SciLibra. Give it a try, and experience the convenience of an all-in-one solution for scientific article management.

## Requirements
To run SciLibra, make sure you have Python, Kivy, and pylatexenc installed on your system. Refer to the "Requirements" section in this README for installation instructions.



## About Author
- **Created by:** Alsamman M. Alsamman
- **Emails:** smahmoud [at] ageri.sci.eg, A.Alsamman [at] cgiar.org, SammanMohammed [at] gmail.com
- **License:** [MIT License](https://opensource.org/licenses/MIT)
- **Disclaimer:** The script comes with no warranty, use at your own risk
- **This script is not intended for commercial use**

## Usage

python SciLibra.py

